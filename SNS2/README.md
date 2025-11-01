# Secure Telemedical System

## Overview
This project implements a secure telemedical system allowing confidential doctor-patient consultations using robust cryptographic protocols. The system ensures secure authentication, data access control, and encrypted communication, meeting essential requirements for telemedical platforms.

## System Architecture

The system consists of two main components:
- **Doctor Server**: Acts as the Gateway Node (GWN) that manages multiple patient connections
- **Patient Client**: Connects to the doctor server and establishes secure communication

### Security Features

- **Authentication**: ElGamal-based cryptographic authentication
- **Key Exchange**: Secure session key exchange using ElGamal cryptosystem
- **Encrypted Communication**: AES-256 encryption for message confidentiality
- **Message Integrity**: Cryptographic signatures to verify message authenticity
- **Broadcast Capability**: Secure message broadcasting using a group key

## Implementation

### Cryptographic Building Blocks

1. **ElGamal Cryptosystem**:
   - Key generation using large primes for discrete logarithm problem intractability
   - Public key: (p, g, y) where y = g^x mod p
   - Private key: x

2. **Digital Signatures**:
   - ElGamal-based signatures to authenticate messages
   - Verification process to confirm identity and message integrity

3. **Symmetric Encryption**:
   - AES-256 for efficient and secure message encryption
   - Used with session keys established during authentication

### Authentication Protocol

The system implements a 3-phase protocol:

1. **Phase 1: Initialization**
   - Generation of cryptographic keypairs
   - Establishment of secure identities

2. **Phase 2: Authentication and Key Exchange**
   - Timestamp-based verification to prevent replay attacks
   - Random nonce generation for session freshness
   - Session key agreement and verification

3. **Phase 3: Secure Message Broadcasting**
   - Group key computation from individual session keys
   - Encrypted broadcast messaging to all authenticated patients

## Communication Protocol

The system uses the following opcodes to manage communication:

| Opcode | Message Type | Description |
|--------|--------------|-------------|
| 10 | KEY_VERIFICATION | A device and GWN verify the established keys |
| 20 | SESSION_TOKEN | GWN sends an encrypted session token |
| 30 | GROUP_KEY | Encrypted group key established by the server |
| 40 | ENC_MSG | Emergency message broadcasted by GWN |
| 50 | DEC_MSG | Emergency message decrypted at clients using group key |
| 60 | DISCONNECT | End the session for all participants |

## Performance Analysis

The implementation measures execution time for various cryptographic primitives:

| Operation | Average Time (s) |
|-----------|------------------|
| ElGamal Key Generation | 0.053737 |
| AES-256 Encryption | 0.002555 |
| AES-256 Decryption | 0.000337 |
| Broadcast Message | 0.000845 |

## Setup and Usage Instructions

### Requirements
- Python 3.7 or higher
- Required packages: pycryptodome, cryptography

### Installation
```bash
pip install pycryptodome cryptography
```

### Running the Doctor Server
```bash
python doctor.py --id [DOCTOR_ID]
```

### Running the Patient Client
```bash
python patient.py --id [PATIENT_ID] --doctor_id [DOCTOR_ID]
```

### Doctor Command Interface
1. List connected patients
2. Broadcast message to all patients
3. Disconnect all patients
4. Exit server

### Patient Command Interface
1. Send disconnect request
2. Exit client

## Security Considerations

- The system implements timestamp verification with configurable tolerance to prevent replay attacks
- Cryptographic signatures confirm message authenticity and integrity
- Session keys are securely exchanged and verified before communication begins
- Group key broadcasting enables secure one-to-many communication

## Code Structure

- **doctor.py**: Implementation of the doctor server (Gateway Node)
- **patient.py**: Implementation of the patient client
- **utils.py**: Utility functions for cryptographic operations

## Limitations and Future Work

- The current implementation uses a fixed network configuration (localhost)
- A more scalable solution would involve database integration for patient records
- Additional security features like certificate-based authentication could be implemented
- The system could be extended to support multiple doctor nodes

## License

IIIT-Hyderabad SNS Course'25

## Contributors

Junaid Ahmed (2024201018)
Nikhil Saxena (2024201034)
Swarnadeep Saha (2024201049)

