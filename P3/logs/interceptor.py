import grpc
import time
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Configure server-side logging
server_logger = logging.getLogger('server_interceptor')
server_logger.setLevel(logging.INFO)
server_handler = RotatingFileHandler(
    'server_logs.txt',
    maxBytes=1024*1024,  # 1MB
    backupCount=5
)
server_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
server_logger.addHandler(server_handler)

# Configure client-side logging
client_logger = logging.getLogger('client_interceptor')
client_logger.setLevel(logging.INFO)
client_handler = RotatingFileHandler(
    'client_logs.txt',
    maxBytes=1024*1024,  # 1MB
    backupCount=5
)
client_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
client_logger.addHandler(client_handler)

class ServerLoggingInterceptor(grpc.ServerInterceptor):
    def __init__(self):
        self._valid_metadata = ('auth-key', 'request-id')

    def intercept_service(self, continuation, handler_call_details):
        """Intercept and log incoming requests.
        
        Args:
            continuation: Function that continues processing the call
            handler_call_details: Details about the call
        """
        # Log the incoming request
        method_name = handler_call_details.method
        metadata = dict(handler_call_details.invocation_metadata)
        
        # Use server_logger instead of logger
        server_logger.info(f"Received request: {method_name}")
        server_logger.info(f"Request metadata: {metadata}")
        
        # Log timestamp for request tracking
        server_logger.info(f"Request timestamp: {datetime.now().isoformat()}")

        # You can add authentication logic here if needed
        # for key in self._valid_metadata:
        #     if key not in metadata:
        #         return self._abort(grpc.StatusCode.UNAUTHENTICATED, f"Missing {key}")

        # Log the continuation of the request
        response = continuation(handler_call_details)
        server_logger.info(f"Completed processing request: {method_name}")
        
        return response

    def _abort(self, code, details):
        """Helper method to abort the call with specific status code and details."""
        def terminate(ignored_request, context):
            server_logger.error(f"Request aborted: {details}")
            context.abort(code, details)
        return grpc.unary_unary_rpc_method_handler(terminate)

class ClientLoggingInterceptor(grpc.UnaryUnaryClientInterceptor,
                             grpc.UnaryStreamClientInterceptor,
                             grpc.StreamUnaryClientInterceptor,
                             grpc.StreamStreamClientInterceptor):
                             
    def __init__(self):
        self._method_timings = {}

    def _log_call(self, method, request, response, error=None, duration=None):
        client_logger.info(
            f"gRPC Call - Method: {method}, "
            f"Request: {request}, "
            f"Response: {response}, "
            f"Error: {error}, "
            f"Duration: {duration:.2f}s if duration else 'N/A'"
        )

    def intercept_unary_unary(self, continuation, client_call_details, request):
        start_time = time.time()
        try:
            response = continuation(client_call_details, request)
            duration = time.time() - start_time
            self._log_call(
                client_call_details.method,
                request,
                response,
                duration=duration
            )
            return response
        except Exception as e:
            duration = time.time() - start_time
            self._log_call(
                client_call_details.method,
                request,
                None,
                error=str(e),
                duration=duration
            )
            raise

    def intercept_unary_stream(self, continuation, client_call_details, request):
        start_time = time.time()
        try:
            response_iterator = continuation(client_call_details, request)
            responses = [response for response in response_iterator]
            duration = time.time() - start_time
            self._log_call(
                client_call_details.method,
                request,
                responses,
                duration=duration
            )
            return iter(responses)
        except Exception as e:
            duration = time.time() - start_time
            self._log_call(
                client_call_details.method,
                request,
                None,
                error=str(e),
                duration=duration
            )
            raise

    def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        start_time = time.time()
        requests = [request for request in request_iterator]
        try:
            response = continuation(client_call_details, iter(requests))
            duration = time.time() - start_time
            self._log_call(
                client_call_details.method,
                requests,
                response,
                duration=duration
            )
            return response
        except Exception as e:
            duration = time.time() - start_time
            self._log_call(
                client_call_details.method,
                requests,
                None,
                error=str(e),
                duration=duration
            )
            raise

    def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
        start_time = time.time()
        requests = [request for request in request_iterator]
        try:
            response_iterator = continuation(client_call_details, iter(requests))
            responses = [response for response in response_iterator]
            duration = time.time() - start_time
            self._log_call(
                client_call_details.method,
                requests,
                responses,
                duration=duration
            )
            return iter(responses)
        except Exception as e:
            duration = time.time() - start_time
            self._log_call(
                client_call_details.method,
                requests,
                None,
                error=str(e),
                duration=duration
            )
            raise