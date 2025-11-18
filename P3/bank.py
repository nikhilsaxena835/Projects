import grpc
from concurrent import futures
import threading
import time

import pablo_pb2_grpc as protocol_pb2_grpc
import pablo_pb2 as protocol_pb2
import uuid
import json
from interceptor import AuthInterceptor

class BankServer(protocol_pb2_grpc.BankingServicer):
    def __init__(self, bank_name, port):
        self.bank_name = bank_name
        self.port = int(port)
        self.accounts = {}
        self.load_accounts()

        self.transaction_log = set()
        self.prepared_transactions = {}  # transaction_id -> {account, amount, is_credit}
        self.transaction_timeout = 30  # seconds
        self.transaction_lock = threading.Lock()
        
        self.gateway_address = "localhost:50051"
        self.gateway_connected = False
        self.reconnect_thread = None
        self.reconnect_thread_running = False
        self.reconnect_interval = 5  # seconds
        self.gateway_health_check_interval = 10  # seconds
        
        self.cleanup_thread = threading.Thread(target=self._cleanup_transactions, daemon=True)
        self.cleanup_thread.start()
        
        self.gateway_status_lock = threading.Lock()

    def load_accounts(self):
            with open('./comms/dummy.json', 'r') as f:
                data = json.load(f)
                
            for account in data['accounts']:
                if account['bank_name'] == self.bank_name:
                    self.accounts[account['id']] = {
                        'balance': account['bal'],
                        'password': account['password']
                    }
            
            print(f"Loaded {len(self.accounts)} accounts for {self.bank_name}")
            
    def _cleanup_transactions(self):
        while True:
            time.sleep(10) 
            current_time = time.time()
            with self.transaction_lock:
                expired_transactions = []
                for tx_id, tx_data in self.prepared_transactions.items():
                    if current_time - tx_data['timestamp'] > self.transaction_timeout:
                        expired_transactions.append(tx_id)
                
                for tx_id in expired_transactions:
                    print(f"Transaction {tx_id} expired - automatic abort")
                    self._abort_transaction(tx_id)

    def _abort_transaction(self, transaction_id):
        with self.transaction_lock:
            if transaction_id in self.prepared_transactions:
                print(f"Aborting transaction {transaction_id}")
                del self.prepared_transactions[transaction_id]

    def PrepareTransaction(self, request, context):
        transaction_id = request.transaction_id
        account_id = request.account_id
        amount = request.amount
        is_credit = request.is_credit
        
        try:
            with self.transaction_lock:
                if transaction_id in self.prepared_transactions:
                    print(f"Transaction {transaction_id} already prepared")
                    return protocol_pb2.PrepareResponse(transaction_id=transaction_id, ready=True)
                
                if account_id not in self.accounts:
                    print(f"Account {account_id} not found for prepare")
                    return protocol_pb2.PrepareResponse(transaction_id=transaction_id, ready=False)
                
                if not is_credit and self.accounts[account_id]['balance'] < amount:
                    print(f"Insufficient funds in account {account_id} for transaction {transaction_id}")
                    return protocol_pb2.PrepareResponse(transaction_id=transaction_id, ready=False)
                
                self.prepared_transactions[transaction_id] = {
                    'account': account_id,
                    'amount': amount,
                    'is_credit': is_credit,
                    'timestamp': time.time()
                }
                
                print(f"Transaction {transaction_id} prepared successfully")
                return protocol_pb2.PrepareResponse(transaction_id=transaction_id, ready=True)
        
        except Exception as e:
            print(f"Error preparing transaction {transaction_id}: {e}")
            return protocol_pb2.PrepareResponse(transaction_id=transaction_id, ready=False)

    def CommitTransaction(self, request, context):
        transaction_id = request.transaction_id
        should_commit = request.commit
        
        try:
            with self.transaction_lock:
                if transaction_id not in self.prepared_transactions:
                    print(f"Transaction {transaction_id} not found for commit/abort")
                    return protocol_pb2.Status(trx=transaction_id, success=False)
                
                tx_data = self.prepared_transactions[transaction_id]
                account_id = tx_data['account']
                amount = tx_data['amount']
                is_credit = tx_data['is_credit']
                
                if should_commit:
                    if is_credit:
                        self.accounts[account_id]['balance'] += amount
                        print(f"Committed: Credited {amount} to account {account_id}")
                    else:
                        self.accounts[account_id]['balance'] -= amount
                        print(f"Committed: Debited {amount} from account {account_id}")
                    
                    self.transaction_log.add(transaction_id)
                    print(f"Transaction {transaction_id} committed successfully")
                    
                del self.prepared_transactions[transaction_id]
                
                return protocol_pb2.Status(trx=transaction_id, success=True)
        
        except Exception as e:
            print(f"Error in commit phase for transaction {transaction_id}: {e}")
            return protocol_pb2.Status(trx=transaction_id, success=False)

    def ValidateClientDetails(self, client_id, password):
        if client_id not in self.accounts:
            return False
        return self.accounts[client_id]['password'] == password
    
    def Registration(self, request, context):
        try:
            if request.ID:  
                if not self.ValidateClientDetails(request.ID, request.password):
                    print(f"Invalid client details for {request.ID}")
                    return protocol_pb2.Status(trx=request.trx, success=False)
                
                print(f"Client {request.ID} validated successfully")
                return protocol_pb2.Status(trx=request.trx, success=True)
            else:
                return protocol_pb2.Status(trx=request.trx, success=False)
        
        except Exception as e:
            print(f"Registration validation error: {e}")
            return protocol_pb2.Status(trx=request.trx, success=False)

    def CheckBalance(self, request, context):
        try:
            client_id = request.trx
            if client_id not in self.accounts:
                print(f"Account not found: {client_id}")
                return protocol_pb2.Credit(amount=-1, trx="error")

            balance = self.accounts[client_id]['balance']
            print(f"Balance check for {client_id}: {balance}")
            return protocol_pb2.Credit(amount=balance, trx="success")

        except Exception as e:
            print(f"Error checking balance: {e}")
            return protocol_pb2.Credit(amount=-1, trx="error")
        
    def MakePayment(self, request, context):
        transaction_id = request.trx
        sender_id = request.init_id
        receiver_id = request.recv_id
        receiver_bank = request.recv_bank
        amount = request.amount
        is_credit = request.credit
        
        try:
            with self.transaction_lock:
                print(f"[MakePayment] Processing transaction {transaction_id}: {sender_id} -> {receiver_id} ({receiver_bank}), amount={amount}, credit={is_credit}")
                
                # Validate sender
                if sender_id not in self.accounts:
                    print(f"[MakePayment] Sender account {sender_id} not found")
                    return protocol_pb2.TransactionInitResponse(success=False, error_message=f"Sender account {sender_id} not found")
                
                # Validate receiver (same bank for simplicity)
                if receiver_bank != self.bank_name:
                    print(f"[MakePayment] Receiver bank {receiver_bank} does not match server bank {self.bank_name}")
                    return protocol_pb2.TransactionInitResponse(success=False, error_message=f"Receiver bank {receiver_bank} not supported")
                
                if receiver_id not in self.accounts:
                    print(f"[MakePayment] Receiver account {receiver_id} not found")
                    return protocol_pb2.TransactionInitResponse(success=False, error_message=f"Receiver account {receiver_id} not found")
                
                # Check sender's balance
                if not is_credit and self.accounts[sender_id]['balance'] < amount:
                    print(f"[MakePayment] Insufficient funds in account {sender_id}: balance={self.accounts[sender_id]['balance']}, required={amount}")
                    return protocol_pb2.TransactionInitResponse(success=False, error_message=f"Insufficient funds in account {sender_id}")
                
                # Process transaction
                if is_credit:
                    self.accounts[receiver_id]['balance'] += amount
                    print(f"[MakePayment] Credited {amount} to receiver {receiver_id}")
                else:
                    self.accounts[sender_id]['balance'] -= amount
                    self.accounts[receiver_id]['balance'] += amount
                    print(f"[MakePayment] Debited {amount} from sender {sender_id}, credited {amount} to receiver {receiver_id}")
                
                # Log transaction
                self.transaction_log.add(transaction_id)
                print(f"[MakePayment] Transaction {transaction_id} completed successfully")
                return protocol_pb2.TransactionInitResponse(success=True)
        
        except Exception as e:
            print(f"[MakePayment] Error processing transaction {transaction_id}: {str(e)}")
            return protocol_pb2.TransactionInitResponse(success=False, error_message=f"Error: {str(e)}")

    def get_gateway_credentials(self):
        try:
            with open("certs/bank.key", "rb") as f:
                private_key = f.read()
            with open("certs/bank.crt", "rb") as f:
                certificate_chain = f.read()
            with open("certs/gateway.crt", "rb") as f:
                root_certificates = f.read()

            credentials = grpc.ssl_channel_credentials(
                root_certificates=root_certificates,
                private_key=private_key,
                certificate_chain=certificate_chain
            )
            return credentials
        except Exception as e:
            print(f"Error loading credentials: {e}")
            return None

    def check_gateway_health(self, stub):
        try:
            health_check_request = protocol_pb2.Ping(alive = True)
            stub.Pinger(health_check_request, timeout=2)
            return True
        except Exception:
            print("This returned false ?? ")
            return False

    def register_with_gateway(self, gateway_address=None):
        if gateway_address:
            self.gateway_address = gateway_address
            
        try:
            credentials = self.get_gateway_credentials()
            if not credentials:
                print("Failed to get credentials")
                with self.gateway_status_lock:
                    self.gateway_connected = False
                return False
                
            channel = grpc.secure_channel(self.gateway_address, credentials)
            stub = protocol_pb2_grpc.BankingStub(channel)
            
            registration_request = protocol_pb2.Register(
                IP="localhost",
                port=int(self.port),
                name=self.bank_name,
                ID="",
                password="",
                trx=str(uuid.uuid4())
            )
            
            response = stub.Registration(registration_request, timeout=5)
            if response.success:
                print(f"Bank {self.bank_name} registered successfully with gateway")
                with self.gateway_status_lock:
                    self.gateway_connected = True
                    self.gateway_stub = stub  
                    self.gateway_channel = channel 
                return True
            else:
                print("Failed to register with gateway")
                with self.gateway_status_lock:
                    self.gateway_connected = False
                return False
                
        except grpc.RpcError as e:
            with self.gateway_status_lock:
                self.gateway_connected = False
            print(f"gRPC error connecting to gateway: {e.code()}: {e.details()}")
            return False
        except Exception as e:
            with self.gateway_status_lock:
                self.gateway_connected = False
            print(f"Failed to register with gateway: {e}")
            return False
            
    def check_gateway_and_reconnect(self):
        self.reconnect_thread_running = True
        last_attempt_time = 0
        while self.reconnect_thread_running:
            current_time = time.time()
            reconnect_needed = False
        
            with self.gateway_status_lock:
                if self.gateway_connected:
                    if not self.check_gateway_health(self.gateway_stub):
                        print("Gateway connection lost. Will attempt to reconnect...")
                        self.gateway_connected = False
                        reconnect_needed = True
                        if hasattr(self, 'gateway_channel'):
                            try:
                                self.gateway_channel.close()
                            except:
                                pass
                elif current_time - last_attempt_time >= self.reconnect_interval:
                    reconnect_needed = True
            
            if reconnect_needed:
                print(f"Attempting to connect to gateway at {self.gateway_address}...")
                last_attempt_time = current_time
                if self.register_with_gateway():
                    print("Successfully connected to gateway!")
                else:
                    print(f"Gateway unavailable. Retrying in {self.reconnect_interval} seconds...")
            
            time.sleep(self.gateway_health_check_interval)
    
    def start_reconnect_thread(self):
        if self.reconnect_thread is None or not self.reconnect_thread.is_alive():
            self.reconnect_thread = threading.Thread(
                target=self.check_gateway_and_reconnect,
                daemon=True
            )
            self.reconnect_thread.start()
            
    def stop_reconnect_thread(self):
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            self.reconnect_thread_running = False
            self.reconnect_thread.join(timeout=2)
            print("Stopped gateway connection monitoring thread")
            

def serve(bank_name, port, gateway_address):
    interceptors = [AuthInterceptor()]
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), interceptors=interceptors)
    bank_servicer = BankServer(bank_name, port)
    protocol_pb2_grpc.add_BankingServicer_to_server(bank_servicer, server)
    
    with open("certs/bank.key", "rb") as f:
        private_key = f.read()
    with open("certs/bank.crt", "rb") as f:
        certificate_chain = f.read()
    with open("certs/ca.crt", "rb") as f:
        root_certificates = f.read()

    server_credentials = grpc.ssl_server_credentials(
        [(private_key, certificate_chain)],
        root_certificates=root_certificates,
        require_client_auth=True
    )

    server.add_secure_port(f'[::]:{port}', server_credentials)
    server.start()
    bank_servicer.start_reconnect_thread()
    
    print(f"Bank server {bank_name} started on port {port}")
    
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        bank_servicer.stop_reconnect_thread()
        server.stop(0)
        print("Bank server shutting down...")

if __name__ == "__main__":
    bank_name = input("Enter Bank Name: ")
    port = input("Enter port number : ")
    serve(bank_name, port, f"localhost:50051")