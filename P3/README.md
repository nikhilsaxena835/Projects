## 1. Introduction
This report details the design, implementation, and security mechanisms of a miniature Stripe-like payment gateway system using gRPC. The system consists of three main components: 
1. **Bank Servers** - Represent individual banks handling transactions.
2. **Clients** - Users interacting with the payment gateway.
3. **Payment Gateway** - The intermediary handling secure payments between clients and banks.

## 2. System Components
### 2.1 Bank Servers
- Maintain account balances.
- Validate transactions to ensure funds availability.
- Handle debit and credit operations as instructed by the payment gateway.
- Implements a two-phase commit protocol.
- Automatic reconnection to the payment gateway
- Cleanup mechanism to handle expired operations.



### 2.2 Clients
Clients are users interacting with the payment system. Each client:
- Registers with the payment gateway.
- Provides account details linked to a bank.
- Can initiate payments and check balances.

### 2.3 Payment Gateway
The gateway serves as a central hub that:
- Authenticates and authorizes clients.
- Facilitates transactions between clients and banks.
- Implements security mechanisms including encryption and logging.




## 3. Authentication, Authorization, and Logging
### 3.1 Authentication
- Clients authenticate using stored credentials (preloaded in a JSON file for simulation).
- SSL/TLS ensures encrypted communication, protecting against eavesdropping.
- gRPC handles secure credential verification between clients and the payment gateway.
- **Authentication Interceptor**: Ensures that all incoming requests have valid credentials before processing.
### 3.2 Authorization
Authorization is enforced using gRPC interceptors. Clients are only permitted to:
- View their own balances.
- Access specific services based on predefined roles.
- **Authorization Interceptor**: Grants or denies access based on user roles and permissions.
### 3.3 Logging
Logging is implemented to capture:
- Transaction details (amount, client ID, method name, errors, retries).
- Authentication and authorization attempts.
- All gRPC request-response interactions for debugging.
- **Logging Interceptor**: Captures request metadata, execution times, and errors for monitoring.


## 4. Idempotent Payments
To prevent duplicate deductions:
- Each transaction is assigned a unique ID given by `uiud4()`.
- The payment gateway stores processed transaction IDs to prevent re-processing.
- Timestamps are **not** used due to scalability concerns.
- This ensures that multiple identical requests produce the same result. 

**Proof of Correctness**
1. Each transaction ID is generated uniquely at the client side.
2. The payment gateway maintains a database of processed transactions.
3. If a retry occurs, the gateway checks its records before proceeding.
4. If the transaction ID exists, it is ignored, ensuring correctness.

## 5. Offline Payments Handling
If a client is offline, the following approach is used:
- Payments are queued locally at the client.
- Once connectivity is restored, queued payments are sent.
- The client checks server acknowledgment before removing the payment from the queue.
- This mechanism ensures that failed transactions do not get lost.

## 6. Two-Phase Commit (2PC) with Timeout
The 2PC protocol is implemented as follows:
1. **Prepare Phase**:
   - The payment gateway sends a prepare request to both the sender's and receiver’s banks.

    - `PrepareTransaction` checks if the transaction can be executed based on available balance.
    - If valid, the transaction is stored in `prepared_transactions` with a timestamp.
    - Transactions with insufficient funds or invalid accounts are rejected.
    - If all banks respond affirmatively, the gateway proceeds with the commit phase.
2. **Commit Phase**:
    - If any bank aborts or times out, the transaction is canceled.
    - A timeout mechanism ensures that unresolved transactions are rolled back.
    - If aborted or expired, the transaction is removed from `prepared_transactions` via a cleanup thread (`_cleanup_transactions`) that runs periodically
    - If committed, funds are credited or debited accordingly.
    - `CommitTransaction` finalizes a prepared transaction based on the commit request.

## 7. gRPC Service Definitions (Proto Files)

The `Banking` gRPC service defines messages to represent transaction details, registration requests, and system status updates. Below are the message definitions and rpc calls:

### Message Definitions

1. **TransactionInit**
   - Represents an initial payment request from a client to the payment gateway.
   - Fields:
     - `init_id`: ID of the initiator.
     - `recv_id`: ID of the receiver.
     - `recv_bank`: Bank of the receiver/sender.
     - `amount`: Payment amount.
     - `trx`: Unique transaction identifier.
     - `credit`: Indicates whether the transaction is a credit operation.

2. **TrxInfo**
   - Sent by the gateway to banks for debiting or crediting.
   - Fields:
     - `id`: Account ID involved in the transaction.
     - `amount`: Amount being transacted.
     - `trx`: Transaction identifier.
     - `credit`: Indicates whether this is a credit operation.

3. **Status**
   - Used to indicate transaction status across different components.
   - Fields:
     - `trx`: Transaction identifier.
     - `success`: Boolean indicating success or failure.

4. **Credit**
   - Represents a credit transaction sent from the receiver client to the gateway.
   - Fields:
     - `amount`: Amount credited.
     - `trx`: Transaction identifier.

5. **Register**
   - Used for registering clients and banks with the gateway.
   - Fields:
     - `IP`: IP address of the registering entity.
     - `port`: Port number.
     - `name`: Entity name (bank or client).
     - `ID`: Unique client ID (null for banks).
     - `password`: Authentication password (null for banks).
     - `trx`: Transaction identifier.

6. **PrepareRequest**
   - Used in the two-phase commit protocol to prepare a transaction.
   - Fields:
     - `transaction_id`: Unique identifier of the transaction.
     - `account_id`: Account involved in the transaction.
     - `amount`: Amount being transacted.
     - `is_credit`: Boolean indicating credit operation.

7. **PrepareResponse**
   - Response to `PrepareRequest`, indicating readiness to commit.
   - Fields:
     - `transaction_id`: Transaction identifier.
     - `ready`: Boolean indicating readiness.

8. **CommitRequest**
   - Final step in the two-phase commit protocol to commit or abort a transaction.
   - Fields:
     - `transaction_id`: Transaction identifier.
     - `commit`: Boolean indicating whether to commit (`true`) or abort (`false`).

9. **Ping**
   - Used to check the health status of a server.
   - Fields:
     - `alive`: Boolean indicating if the service is responsive.


### gRPC Service Methods

The `Banking` service exposes multiple RPCs to handle transaction processing and client interactions:

1. **MakePayment (TransactionInit) → Status**
   - Initiates a payment from a sender to the payment gateway.
   - The gateway processes the transaction and returns a status update.

2. **UpdateBalance (TrxInfo) → Status**
   - Instructs banks to debit or credit accounts based on the provided transaction details.
   - Returns success or failure status.

3. **CreditMoney (Credit) → Status**
   - Used by the receiver client to notify the gateway that funds have been credited.
   - The gateway updates the transaction status accordingly.

4. **CheckBalance (Status) → Credit**
   - Allows clients to check their balance by sending a request to the gateway.
   - The gateway forwards the request to the respective bank and returns the balance information.

5. **Registration (Register) → Status**
   - Registers a bank or client with the payment gateway.
   - Returns a status update confirming successful or failed registration.

6. **PrepareTransaction (PrepareRequest) → PrepareResponse**
   - Part of the two-phase commit process.
   - Asks banks if they are ready to process a transaction before committing.
   - Returns readiness status.

7. **CommitTransaction (CommitRequest) → Status**
   - Finalizes a transaction in the two-phase commit protocol.
   - Based on the commit request, the transaction is either committed or aborted.

8. **Pinger (Ping) → Ping**
   - Simple health check RPC to verify service availability.


#### Payment Processing Flow
1. A client initiates a payment via `MakePayment`.
2. The gateway validates and forwards debit/credit requests via `UpdateBalance`.
3. Banks process the transaction and send a `Status` update.
4. For the two-phase commit:
   - The gateway sends `PrepareTransaction` to banks.
   - Banks respond with `PrepareResponse`.
   - The gateway sends `CommitTransaction` to finalize the transaction.
5. The receiver confirms credit via `CreditMoney`.
6. The client can check their balance via `CheckBalance`.
7. Registration of banks and clients occurs via `Registration`.



LLM

    -Certificate generator
    -This report