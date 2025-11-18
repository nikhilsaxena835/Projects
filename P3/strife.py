import grpc
from concurrent import futures
import pablo_pb2_grpc as protocol_pb2_grpc
import pablo_pb2 as protocol_pb2
import threading
import time
from interceptor import AuthInterceptor

GATEWAY_PORT = 50051
TRANSACTION_CLEANUP_TIME = 10

class PaymentGateway(protocol_pb2_grpc.BankingServicer):
    def __init__(self):
        self.bank_addresses = {}  # bank_name -> address
        self.client_addresses = {}  # client_id -> (address, bank_name)
        self.address_lock = threading.Lock()
        self.bank_stubs = {} # bank_name -> channel
        self.stub_lock = threading.Lock()
        self.transaction_log = {}  # trans_id -> time
        self.cleanup_thread = threading.Thread(target=self._cleanup_transactions, daemon=True)
        self.cleanup_thread.start()

        self.transaction_timeout = 30  # seconds
        self.in_progress_transactions = {}

        with open("certs/gateway.key", "rb") as f:
            self.private_key = f.read()
        with open("certs/gateway.crt", "rb") as f:
            self.certificate_chain = f.read()
        with open("certs/bank.crt", "rb") as f:
            self.bank_root_certificates = f.read()

    def get_secure_bank_channel(self, address):
        credentials = grpc.ssl_channel_credentials(
            root_certificates=self.bank_root_certificates,
            private_key=self.private_key,
            certificate_chain=self.certificate_chain
        )
        
        return grpc.secure_channel(address, credentials)

    def Registration(self, request, context):
        try:
            address = f"{request.IP}:{int(request.port)}"
            if request.ID:  # Client registration
                if not request.password:
                    return protocol_pb2.Status(trx=request.trx, success=True)
                bank_name = request.name
                if bank_name not in self.bank_stubs:
                    print(f"Unknown bank: {bank_name}")
                    return protocol_pb2.Status(trx=request.trx, success=False)
                
                validation_response = self.bank_stubs[bank_name].Registration(request)
                if not validation_response.success:
                    print(f"Bank validation failed for client {request.ID}")
                    return protocol_pb2.Status(trx=request.trx, success=False)
                
                with self.address_lock:
                    self.client_addresses[request.ID] = (address, request.name)
                    print(f"Registered client {request.ID} at {address} with bank {request.name}")
            
            else:  # Bank registration
                with self.address_lock:
                    if not request.password:
                        self.bank_addresses[request.name] = address
                        channel = self.get_secure_bank_channel(address)
                        self.bank_stubs[request.name] = protocol_pb2_grpc.BankingStub(channel)
                        print(f"Registered bank {request.name} at {address}")
            
            return protocol_pb2.Status(trx=request.trx, success=True)
        except Exception as e:
            print(f"Registration error: {e}")
            return protocol_pb2.Status(trx=request.trx, success=False)

    def CheckBalance(self, request, context):
        try:
            client_id = request.trx 
            if client_id not in self.client_addresses:
                print(f"Unknown client: {client_id}")
                return protocol_pb2.Credit(amount=-1, trx="error")

            bank_name = self.client_addresses[client_id][1]
            if bank_name not in self.bank_stubs:
                print(f"Unknown bank: {bank_name}")
                return protocol_pb2.Credit(amount=-1, trx="error")

            balance_request = protocol_pb2.Status(trx=client_id)
            balance = self.bank_stubs[bank_name].CheckBalance(balance_request)
            return balance

        except Exception as e:
            print(f"Balance check error: {e}")
            return protocol_pb2.Credit(amount=-1, trx="error")
            
    def _prepare_transaction(self, tid, request, sender_bank, receiver_bank):
        for bank, account, is_credit in [
            (sender_bank, request.init_id, False),
            (receiver_bank, request.recv_id, True)]:
            
            prep = protocol_pb2.PrepareRequest(
                transaction_id=tid,
                account_id=account,
                amount=request.amount,
                is_credit=is_credit
            )
            try:
                if not self.bank_stubs[bank].PrepareTransaction(prep).ready:
                    print(f"Bank not ready: {bank}")
                    return False
            except grpc.RpcError as e:
                print(f"Prepare failed at {bank}: {e}")
                return False
        self._update_transaction_state(tid, "prepared")
        return True

    def _commit_transaction(self, tid, sender_bank, receiver_bank, request):
        commit_req = protocol_pb2.CommitRequest(transaction_id=tid, commit=True)
        try:
            if not self.bank_stubs[sender_bank].CommitTransaction(commit_req).success:
                print(f"Sender commit failed: {tid}")
                return False
            if not self.bank_stubs[receiver_bank].CommitTransaction(commit_req).success:
                print(f"Receiver commit failed: {tid}")
                self._rollback_debit(sender_bank, request.init_id, request.amount, tid)
                return False
            return True
        except grpc.RpcError as e:
            print(f"Commit error: {e}")
            self._rollback_debit(sender_bank, request.init_id, request.amount, tid)
            return False
    
    
    def MakePayment(self, request, context):
        transaction_id = request.trx
        current_time = time.time()
        
        with self.stub_lock:
            if transaction_id in self.transaction_log:
                print(f"Duplicate transaction: {transaction_id}")
                return protocol_pb2.Status(trx=transaction_id, success=True)
            self.transaction_log[transaction_id] = current_time
        

        sender_bank = request.recv_bank
        receiver_info = self.client_addresses.get(request.recv_id)
        if not (sender_bank in self.bank_stubs and receiver_info and receiver_info[1] in self.bank_stubs):
            print(f"Invalid bank or receiver: {sender_bank}, {request.recv_id}")
            return protocol_pb2.Status(trx=transaction_id, success=False)
        
        receiver_bank_name = receiver_info[1]
        
        with self.stub_lock:
            self.in_progress_transactions[transaction_id] = {
                "state": "preparing",
                "data": {
                    "sender_id": request.init_id,
                    "sender_bank": sender_bank,
                    "receiver_id": request.recv_id,
                    "receiver_bank": receiver_bank_name,
                    "amount": request.amount
                },
                "timestamp": current_time
            }
        
        # 2PC Phase 1: Prepare
        print(f"2PC PREPARE: {transaction_id}")
        if not self._prepare_transaction(transaction_id, request, sender_bank, receiver_bank_name):
            self._abort_transaction(transaction_id)
            return protocol_pb2.Status(trx=transaction_id, success=False)
        
        # 2PC Phase 2: Commit
        print(f"2PC COMMIT: {transaction_id}")
        self._update_transaction_state(transaction_id, "committing")
        if not self._commit_transaction(transaction_id, sender_bank, receiver_bank_name, request):
            self._abort_transaction(transaction_id)
            return protocol_pb2.Status(trx=transaction_id, success=False)
        
        self._update_transaction_state(transaction_id, "committed")
        print(f"Transaction committed: {transaction_id}")
        return protocol_pb2.Status(trx=transaction_id, success=True)

    def Pinger(self, request, context):
        return protocol_pb2.Ping(alive=True)
            
    def _rollback_debit(self, bank_name, client_id, amount, transaction_id):
        rollback_request = protocol_pb2.TrxInfo(
            id=client_id,
            amount=amount,
            trx=f"rollback_{transaction_id}",
            credit=True
        )
            
        self.bank_stubs[bank_name].UpdateBalance(rollback_request)
        print(f"Rolled back debit for transaction {transaction_id}")

    def _update_transaction_state(self, transaction_id, new_state):
        with self.stub_lock:
            if transaction_id in self.in_progress_transactions:
                self.in_progress_transactions[transaction_id]["state"] = new_state
                print(f"Transaction {transaction_id} state updated to: {new_state}")

    def _abort_transaction(self, transaction_id):
        with self.stub_lock:
            if transaction_id not in self.in_progress_transactions:
                print(f"Transaction {transaction_id} not found for abort")
                return
            
            tx_data = self.in_progress_transactions[transaction_id]["data"]

            abort_request = protocol_pb2.CommitRequest(
                transaction_id=transaction_id,
                commit=False  # false means abort
            )
            
            
            try:
                self.bank_stubs[tx_data["sender_bank"]].CommitTransaction(abort_request)
            except Exception as e:
                print(f"Error aborting with sender bank: {e}")
            
            try:
                self.bank_stubs[tx_data["receiver_bank"]].CommitTransaction(abort_request)
            except Exception as e:
                print(f"Error aborting with receiver bank: {e}")
            
            self.in_progress_transactions[transaction_id]["state"] = "aborted"
            print(f"Transaction {transaction_id} aborted")


    def _cleanup_transactions(self):
        while True:
            time.sleep(TRANSACTION_CLEANUP_TIME)
            current_time = time.time()
            with self.stub_lock:
                self.transaction_log = {
                    trx_id: timestamp 
                    for trx_id, timestamp in self.transaction_log.items()
                    if current_time - timestamp < 60  
                }
                
                timed_out_transactions = []
                for tx_id, tx_info in self.in_progress_transactions.items():
                    if current_time - tx_info["timestamp"] > self.transaction_timeout:
                        if tx_info["state"] in ["preparing", "prepared", "committing"]:
                            timed_out_transactions.append(tx_id)
                

                for tx_id in timed_out_transactions:
                    print(f"Transaction {tx_id} timed out - automatic abort")
                    self._update_transaction_state(tx_id, "aborting")
                    
            for tx_id in timed_out_transactions:
                self._abort_transaction(tx_id)

class GatewayServer:
    def __init__(self):
        self.port = GATEWAY_PORT
        self.gateway = PaymentGateway()
        interceptors = [AuthInterceptor()]
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), interceptors=interceptors)

        with open("certs/gateway.key", "rb") as f:
            private_key = f.read()
        with open("certs/gateway.crt", "rb") as f:
            certificate_chain = f.read()
        with open("certs/ca.crt", "rb") as f:
            root_certificates = f.read()  

        self.server_credentials = grpc.ssl_server_credentials(
            [(private_key, certificate_chain)],
            root_certificates=root_certificates,
            require_client_auth=False,
        )

        protocol_pb2_grpc.add_BankingServicer_to_server(self.gateway, self.server)
        self.server.add_secure_port(f'[::]:{self.port}', self.server_credentials)


    def start(self):
        self.server.start()
        print(f"Strife started on port {self.port}")
        try:
            while True:
                time.sleep(86400)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        print("Stopping Strife...")
        self.server.stop(0)
        
if __name__ == "__main__":
    gateway_server = GatewayServer()
    gateway_server.start()