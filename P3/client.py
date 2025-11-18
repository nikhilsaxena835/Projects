import grpc
import uuid
import threading
import time
from datetime import datetime

import pablo_pb2_grpc as protocol_pb2_grpc
import pablo_pb2 as protocol_pb2
from interceptor import ClientInterceptor

HISTORY_LIMIT = 10


class PaymentClient:
    def __init__(self, gateway_address, client_id, client_port, bank_name, password):
        self.client_id = client_id
        self.client_port = int(client_port)
        self.bank_name = bank_name
        self.password = password
        
        self.payment_lock = threading.Lock()
        self.pending_payments = []
        self.transaction_history = []
        self.history_lock = threading.Lock()

        with open("certs/client.key", "rb") as f:
            self.private_key = f.read()
        with open("certs/client.crt", "rb") as f:
            self.certificate_chain = f.read()
        with open("certs/ca.crt", "rb") as f:
            self.gateway_cert = f.read()
        
        self.channel_credentials = grpc.ssl_channel_credentials(
            root_certificates=self.gateway_cert,
            private_key=self.private_key,
            certificate_chain=self.certificate_chain
        )

        self.gateway_address = gateway_address
        self.reconnect_thread = None
        self.stop_reconnect_thread = threading.Event()
        
        try:
            self.channel = self._return_channel(gateway_address, self.channel_credentials)
            self.stub = protocol_pb2_grpc.BankingStub(self.channel)
            self._register_with_gateway()
            
        except Exception as e:
            print(f"Client initialization error: {e}")
            raise

    def _add_to_history(self, transaction_id, receiver_id, receiver_bank, amount, status, timestamp=None):
        with self.history_lock:
            self.transaction_history.append({
                'transaction_id': transaction_id,
                'receiver_id': receiver_id,
                'receiver_bank': receiver_bank,
                'amount': amount,
                'status': status,
                'timestamp': timestamp or datetime.now().isoformat()
            })

    def _return_channel(self, gateway_address, channel_credentials):
        interceptor = ClientInterceptor(
        client_id = self.client_id,
        password = self.password,
        bank_name = self.bank_name
        )
        channel = grpc.secure_channel(gateway_address, channel_credentials)
        channel = grpc.intercept_channel(channel, interceptor)
        return channel
    
    def _is_transaction_in_history(self, transaction_id):
        with self.history_lock:
            for tx in self.transaction_history:
                if tx['transaction_id'] == transaction_id:
                    return True

            return False

    def show_history(self, limit=HISTORY_LIMIT):
        with self.history_lock:
            if not self.transaction_history:
                return "No transaction history"
            
            recent_transactions = sorted(
                self.transaction_history,
                key=lambda x: x['timestamp'],
                reverse=True
            )[:limit]
            
            history_text = "\nRecent Transactions:\n"
            for tx in recent_transactions:
                history_text += (
                    f"ID: {tx['transaction_id']}\n"
                    f"To: {tx['receiver_id']} (Bank: {tx['receiver_bank']})\n"
                    f"Amount: {tx['amount']}\n"
                    f"Status: {tx['status']}\n"
                    f"Time: {tx['timestamp']}\n"
                    f"{'-' * 50}\n"
                )
            return history_text

    def _get_auth_metadata(self):
        return [
            ('client-id', self.client_id),
            ('password', self.password),
            ('bank-name', self.bank_name),
            ('timestamp', datetime.now().isoformat())
        ]
    
    def retry_transaction(self, transaction_id):
        try:
            with self.history_lock:
                transaction = next(
                    (tx for tx in self.transaction_history if tx['transaction_id'] == transaction_id),
                    None
                )
            
            if not transaction:
                return f"Error: Transaction {transaction_id} not found in history"
            
            print(f"Retrying transaction {transaction_id}")
            return self.send_money(
                transaction['receiver_id'],
                transaction['receiver_bank'],
                transaction['amount'],
                transaction_id
            )
        except Exception as e:
            print(f"Error retrying transaction: {e}")
            return f"Error: {str(e)}"
        

    def list_pending(self):
        with self.payment_lock:
            if not self.pending_payments:
                return "No pending transactions"
            return "\n".join([f"To: {p[0]}, Bank: {p[1]}, Amount: {p[2]}, ID: {p[3]}" 
                            for p in self.pending_payments])

    def force_offline(self):
        if self.channel:
            try:
                self.channel.close()
            except:
                pass
        self.stop_reconnect_thread.set() 
        self.channel = None
        self.stub = None
        print("Client switched to offline mode")
        return "Switched to offline mode"


    def start_reconnect_monitor(self):
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            return
            
        self.stop_reconnect_thread.clear()

        def _monitor_gateway():
            print("Starting gateway connection monitor")
            retry_interval = 5              
            while not self.stop_reconnect_thread.is_set():
                if self.channel is None:
                    # We're offline
                    try:
                        print(f"Attempting to reconnect to gateway at {self.gateway_address}")
                        self.reconnect(self.gateway_address)
                        retry_interval = 5  
                    except Exception as e:
                        print(f"Gateway still offline. Retrying in {retry_interval} seconds... ({str(e)})")
                else:
                    # We have a channel - ping gateway with registration request
                    try:
                        registration_request = protocol_pb2.Ping(
                            alive = True
                        )
                        
                        self.stub.Pinger(
                            registration_request,
                            timeout=2,
                            metadata=self._get_auth_metadata()
                        )
                        # If we reach here, connection is good
                    except Exception as e:
                        print(f"Gateway connection failed: {str(e)}")
                        print("Setting client to offline mode and will attempt to reconnect")
                        if self.channel:
                            try:
                                self.channel.close()
                            except:
                                pass
                        self.channel = None
                        self.stub = None
                
                self.stop_reconnect_thread.wait(retry_interval)
        
        self.reconnect_thread = threading.Thread(target=_monitor_gateway, daemon=True)
        self.reconnect_thread.start()

    def reconnect(self, gateway_address=None):
        if gateway_address:
            self.gateway_address = gateway_address
            
        try:
            self.channel = self._return_channel(self.gateway_address, self.channel_credentials)
            self.stub = protocol_pb2_grpc.BankingStub(self.channel)
            
            self._register_with_gateway()
            
            if self.pending_payments:
                print(f"Found {len(self.pending_payments)} pending transactions to process")
                self.process_pending_payments()
                return f"Reconnected to gateway - processing {len(self.pending_payments)} pending transactions"
            return "Reconnected to gateway"
        except Exception as e:
            print(f"Reconnection error: {e}")
            if self.channel:
                try:
                    self.channel.close()
                except:
                    pass
            self.channel = None
            self.stub = None
            raise

    def _register_with_gateway(self):
        try:
            registration_request = protocol_pb2.Register(
                IP="localhost",
                port=self.client_port,
                name=self.bank_name,
                ID=self.client_id,
                password=self.password,
                trx=str(uuid.uuid4())
            )
            
            response = self.stub.Registration(
                registration_request,
                timeout=10,
                metadata=self._get_auth_metadata()
            )
            
            if response.success:
                print(f"Client {self.client_id} registered successfully with gateway")
                self.start_reconnect_monitor()
                
            else:
                print("Failed to register with gateway")
                raise Exception("Registration failed")
                
        except grpc.RpcError as e:
            print(f"Failed to register with gateway: {e.details() if hasattr(e, 'details') else str(e)}")
            raise
        except Exception as e:
            print(f"Failed to register with gateway: {e}")
            raise

    def check_balance(self):
        try:
            request = protocol_pb2.Status(trx=self.client_id)
            response = self.stub.CheckBalance(
                request,
                metadata=self._get_auth_metadata()
            )
            
            if response.trx == "error":
                print("Failed to get balance")
                return None
                
            return response.amount
            
        except Exception as e:
            print(f"Error checking balance: {e}")
            return None
            
    def _generate_transaction_id(self):
        return str(uuid.uuid4())
        
    def send_money(self, receiver_id, receiver_bank, amount, transaction_id=None):
        def _send_async(receiver_id, receiver_bank, amount, transaction_id):
            try:
                if transaction_id is None:
                    transaction_id = self._generate_transaction_id()
                
                # If this is a retry (receiver_id is None), get details from pending payments
                if receiver_id is None:
                    with self.payment_lock:
                        for payment in self.pending_payments:
                            if payment[3] == transaction_id:
                                receiver_id, receiver_bank, amount, _ = payment
                                break
                        if receiver_id is None:  # Not found in pending, use original transaction_id
                            print(f"Retrying transaction {transaction_id} that's not in pending queue")
                    
                request = protocol_pb2.TransactionInit(
                    init_id=self.client_id,
                    recv_id=receiver_id,
                    recv_bank=receiver_bank,
                    amount=amount,
                    trx=transaction_id,
                    credit=False
                )
                
                print(f"Initiating transaction {transaction_id} to send {amount} to {receiver_id}")
                
                if not self.channel:
                    print("Client is offline, queueing transaction")
                    with self.payment_lock:
                        if not self._is_transaction_in_history(transaction_id):
                            self._add_to_history(transaction_id, receiver_id, receiver_bank, amount, "PENDING - OFFLINE")
                        self.pending_payments.append((receiver_id, receiver_bank, amount, transaction_id))
                    return "Client is offline - transaction queued"
                
                try:
                    response = self.stub.MakePayment(
                        request,
                        metadata=self._get_auth_metadata()
                    )
                    
                    if response.success:
                        print(f"Transaction {transaction_id} completed successfully")
                        # Remove from pending if it was there
                        with self.payment_lock:
                            self.pending_payments = [p for p in self.pending_payments 
                                                if p[3] != transaction_id]
                            if not self._is_transaction_in_history(transaction_id):
                                self._add_to_history(transaction_id, receiver_id, receiver_bank, amount, "SUCCESS")
                        return "Transaction completed successfully"
                    else:
                        print(f"Transaction {transaction_id} failed")
                        with self.payment_lock:
                            if not any(p[3] == transaction_id for p in self.pending_payments):
                                self.pending_payments.append((receiver_id, receiver_bank, amount, transaction_id))
                                if not self._is_transaction_in_history(transaction_id):
                                    self._add_to_history(transaction_id, receiver_id, receiver_bank, amount, "FAILED")
                        return "Transaction failed - added to pending payments"
                        
                except grpc.RpcError as e:
                    print(f"RPC failed: {e}")
                    if e.code() == grpc.StatusCode.UNAVAILABLE:
                        print("Gateway appears to be down. Switching to offline mode")
                        if self.channel:
                            self.channel.close()
                        self.channel = None
                        self.stub = None
                        self.start_reconnect_monitor()
                    
                    with self.payment_lock:
                        if not any(p[3] == transaction_id for p in self.pending_payments):
                            self.pending_payments.append((receiver_id, receiver_bank, amount, transaction_id))
                            if not self._is_transaction_in_history(transaction_id):
                                self._add_to_history(transaction_id, receiver_id, receiver_bank, amount, f"ERROR - {str(e)}")
                    return f"RPC Error: {str(e)}"
                    
            except Exception as e:
                print(f"Unexpected error in send_money: {e}")
                return f"Error: {str(e)}"
        
        thread = threading.Thread(target=_send_async, args=(receiver_id, receiver_bank, amount, transaction_id))
        thread.daemon = True
        thread.start()
        return f"Payment initiated with transaction ID: {transaction_id}  (pending)"
        
    def process_pending_payments(self):
        def _process_async():
            with self.payment_lock:
                if not self.pending_payments:
                    print("No pending payments to process")
                    return
                    
                print(f"Processing {len(self.pending_payments)} pending payments")
                payments_to_process = self.pending_payments.copy()
                
            for receiver_id, receiver_bank, amount, transaction_id in payments_to_process:
                print(f"Retrying pending transaction {transaction_id}")
                self.send_money(receiver_id, receiver_bank, amount, transaction_id)
                time.sleep(1)  
        
        thread = threading.Thread(target=_process_async)
        thread.daemon = True
        thread.start()

def main():
    print("Welcome to the Payment System")
    client_id = input("Enter your client ID: ")
    bank_name = input("Enter your bank name: ")
    password = input("Enter your password: ")
    port = int(input("Enter port number: "))
    
    try:
        client = PaymentClient("localhost:50051", client_id, port, bank_name, password)
        
        while True:
            print("\nAvailable commands:")
            print("1. check - Check your balance")
            print("2. credit <receiver_id> <amount> - Send money")
            print("3. retry <transaction_id> - Retry a specific transaction")
            print("4. pending - List pending transactions")
            print("5. offline - Simulate offline mode")
            print("6. reconnect - Reconnect to gateway")
            print("7. history - Show transaction history")
            print("8. exit - Exit the program")
            
            command = input("\nEnter command: ").split()
            
            if not command:
                time.sleep(1)
                continue
                
            if command[0] == "check":
                balance = client.check_balance()
                if balance is not None:
                    print(f"Current balance: {balance}")
                    
            elif command[0] == "credit" and len(command) == 3:
                receiver_id = command[1]
                try:
                    amount = float(command[2])
                    response = client.send_money(receiver_id, bank_name, amount)
                    print(f"Send money response: {response}")
                except ValueError:
                    print("Invalid amount")
                    
            elif command[0] == "retry" and len(command) == 2:
                transaction_id = command[1]
                response = client.retry_transaction(transaction_id)
                print(f"Retry response: {response}")
                
            elif command[0] == "pending":
                response = client.list_pending()
                print("\nPending Transactions:")
                print(response)
                
            elif command[0] == "offline":
                response = client.force_offline()
                print(response)
                
            elif command[0] == "reconnect":
                response = client.reconnect()
                print(response)
                
            elif command[0] == "exit":
                print("Goodbye!")
                break

            elif command[0] == "history":
                response = client.show_history()
                print(response)
                
            else:
                print("Invalid command")
                
    except Exception as e:
        print(f"Client error: {e}")
        
if __name__ == "__main__":
    main()