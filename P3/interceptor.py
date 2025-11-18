import grpc
import json
import logging

def setup_logging():
    logger = logging.getLogger('payment_system')
    logger.setLevel(logging.INFO)
    
    handler = logging.FileHandler('payment_logs.txt')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

class AuthInterceptor(grpc.ServerInterceptor):
    def __init__(self):
        self.users = self._load_users()
        self.role_perms = {
            'cust': ['MakePayment', 'Registration', 'Pinger'],
            'cashier': ['CheckBalance', 'MakePayment', 'UpdateBalance', 'Registration', 'Pinger'],
            'admin': ['CheckBalance', 'MakePayment', 'UpdateBalance', 'Registration', 'Pinger']
        }
        
    def _load_users(self):
            with open('./comms/dummy.json', 'r') as f:
                data = json.load(f)
                return {account['id']: account for account in data['accounts']}
            
    def _authenticate(self, metadata):
        client_id = dict(metadata).get('client-id')
        password = dict(metadata).get('password')
            
        if not client_id or not password:
            return False, None
                
        if client_id in self.users:
            user = self.users[client_id]
            if user['password'] == password:
                return True, user['role']
        return False, None
 
            
    def _check_authorization(self, method_name, role):
        method = method_name.split('/')[-1]
        return method in self.role_perms.get(role, [])

    def intercept_service(self, continuation, handler_call_details):
        method_name = handler_call_details.method
        
        if 'Pinger' in method_name:
            return continuation(handler_call_details)
            
        metadata = handler_call_details.invocation_metadata
        metadata_dict = dict(metadata)
        
        logger.info(f"Received Request: {method_name}")
        if metadata_dict.get('client-id'): 
            logger.info(f"Client: {metadata_dict.get('client-id')}, Bank: {metadata_dict.get('bank-name')}, Time: {metadata_dict.get('timestamp')}")

        if 'client-id' not in metadata_dict and 'password' not in metadata_dict:
            return continuation(handler_call_details)
            
        is_authenticated, role = self._authenticate(metadata)
        
        if not is_authenticated:
            logger.warning(f"Authentication failed for request to {method_name}")
            return self._abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid credentials")
            
        if not self._check_authorization(method_name, role):
            logger.warning(f"Authorization failed for {role} accessing {method_name}")
            return self._abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")
        
        logger.info(f"Request authorized: {method_name} for role {role}")
        return continuation(handler_call_details)
        
    def _abort(self, code, details):
        def terminate(ignored_request, context):
            context.abort(code, details)
        return grpc.unary_unary_rpc_method_handler(terminate)

class ClientInterceptor(grpc.UnaryUnaryClientInterceptor):    
    def __init__(self, client_id, password, bank_name):
        self.client_id = client_id
        self.password = password
        self.bank_name = bank_name
        
    def intercept_unary_unary(self, continuation, client_call_details, request):
        method = client_call_details.method.decode('utf-8') if isinstance(client_call_details.method, bytes) else client_call_details.method
        method_name = method.split('/')[-1] if '/' in method else method
        
        is_ping = 'Pinger' in method_name
        
        metadata = []
        if client_call_details.metadata is not None:
            metadata = list(client_call_details.metadata)
        
        metadata.extend([
            ('client-id', self.client_id),
            ('password', self.password),
            ('bank-name', self.bank_name),
            ('method', method_name)
        ])
        
        new_details = client_call_details._replace(metadata=metadata)
        
        if not is_ping:
            logger.info(f"Starting request: {method_name}")
            logger.debug(f"Request content: {str(request)}")
        
        try:
            response = continuation(new_details, request)
            
            if not is_ping:
                logger.info(f"Completed {method_name}")
            
            return response
            
        except grpc.RpcError as e:
            status_code = e.code() if hasattr(e, 'code') else 'UNKNOWN'
            details = e.details() if hasattr(e, 'details') else str(e)
            
            if not is_ping:
                logger.error(f"Failed {method_name} with code {status_code}: {details}")
            raise