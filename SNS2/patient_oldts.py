import base64
import os
import socket
import random
import time 
import hashlib 
from cryptography.hazmat.primitives.asymmetric import dh
from math import gcd
import argparse
import threading
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad
import utils

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 9000

def generate_elgamal_keys():
    p, g = utils.get_prime_and_generator()
    x = random.randint(2, p - 2)  # Private key
    y = pow(g, x, p)  # Public key
    return (p, g, y), x  # Public key tuple (p, g, y) and private key x

# Decrypt session key using patient's private key
def decrypt_session_key(cipher_msg, key, p):
    c1, c2 = cipher_msg
    s = pow(c1, key, p)
    s_inv = pow(s, p - 2, p)  
    session_key = (c2 * s_inv) % p
    
    return session_key

def encrypt_session_key(msg, key): #T
    p, g, y = key
    
    if isinstance(msg, bytes):
        msg = int.from_bytes(msg, byteorder='big')
    
    k = random.randint(2, p - 2)       
    
    c1 = pow(g, k, p)
    c2 = (msg * pow(y, k, p)) % p
    
    return c1, c2

def decrypt_with_aes(encrypted_payload, key):
    try:
        if isinstance(key, int):
            key_bytes = key.to_bytes(32, byteorder='big')
        elif isinstance(key, str):
            key_bytes = hashlib.sha256(key.encode()).digest()
        else:
            key_bytes = key
            
        decoded_payload = base64.b64decode(encrypted_payload)
        
        iv = decoded_payload[:16]
        ciphertext = decoded_payload[16:]
        
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted_padded = cipher.decrypt(ciphertext)
        
        decrypted_data = unpad(decrypted_padded, AES.block_size)
        return decrypted_data.decode('utf-8')
    
    except Exception as e:
        print(f"Decryption error: {e}")
        return None

# Generate authentication message for Phase 2
def generate_authMessage(patient_kr, doctor_ku, pid, did, patient_ku):
    K_di_gwn = random.randint(1, 2**128) #This is the session key
    E_ku_gwn = encrypt_session_key(K_di_gwn, doctor_ku)

    tsi = int(time.time()) - 600

    rni = random.randint(1, 2**64)

    data = f"{tsi},{rni},{did},{E_ku_gwn[0]},{E_ku_gwn[1]}"

    signdata = sign_data(data, patient_kr, patient_ku)

    auth_request = {
        "TS_i": tsi,
        "RN_i": rni,
        "ID_GWN": did,
        "encrypted_key": E_ku_gwn,
        "signature": signdata
    }

    return auth_request, K_di_gwn

def sign_data(data, private_key, public_key):
    p, g, y = public_key
    hash_value = int(hashlib.sha256(data.encode()).hexdigest(), 16) % (p-1)
    k = utils.find_coprime(p-1)
    r = pow(g, k, p)
    k_inv = pow(k, -1, p-1) 
    s = (k_inv * (hash_value - private_key * r) % (p-1)) % (p-1)
    
    return (r, s)



def verification(dataToVerify, public_key, sgndata):
    p, g, y = public_key
    sig_r, sig_s = sgndata
    
    if not (1 <= sig_r < p):
        return False
    
    if not (1 <= sig_s < p-1):
        return False

    hash_value = int(hashlib.sha256(dataToVerify.encode()).hexdigest(), 16) % (p-1)

    left_side = pow(g, hash_value, p)
    right_side = (pow(y, sig_r, p) * pow(sig_r, sig_s, p)) % p

    return left_side == right_side

def receive_messages(patient_socket, session_key, doctor_id, patient_id, doctor_public_key, patient_private_key, p):
    group_key = None
    
    try:
        while True:
            try:
                data = patient_socket.recv(4096).decode()
                if not data:
                    print(f"[{utils.get_timestamp()}] Connection closed by doctor")
                    break
                
                parts = data.split(',')
                opcode = parts[0]
                
                if opcode == "30":  # GROUP KEY
                    try:
                        encrypted_payload = parts[1]                        
                            
                        decrypted_group_key = decrypt_with_aes(encrypted_payload, session_key)
                        if decrypted_group_key:
                            group_key = int(decrypted_group_key)
                            print(f"[{utils.get_timestamp()}] Received group key from doctor: {group_key}")
                            print("OPCODE 30 : GROUP KEY (SUCCESS)")
                        else:
                            print(f"[{utils.get_timestamp()}] Failed to decrypt group key")
                    except Exception as e:
                        print(f"[{utils.get_timestamp()}] Error processing group key: {e}")
                

                elif opcode == "40":  # ENCRYPTED MESSAGE
                    with utils.Timer("AES Decryption"):
                        if not group_key:
                            print(f"[{utils.get_timestamp()}] Received encrypted message but no group key available")
                            continue
                        
                        encrypted_payload = parts[1]
                        ts = int(parts[2])
                        sender_id = parts[3]
                        
                        current_time = int(time.time())
                        if abs(current_time - ts) > 5: # 5 seconds tolerance
                            print(f"[{utils.get_timestamp()}] Message timestamp too old, discarding")
                            continue
                        
                        
                        decrypted_message = decrypt_with_aes(encrypted_payload, group_key)
                        message_parts = decrypted_message.split(',', 2)
                        message_ts = int(message_parts[0])
                        message_sender = message_parts[1]
                        actual_message = message_parts[2]
                            
                        if message_ts != ts or message_sender != sender_id:
                            print(f"[{utils.get_timestamp()}] Message verification failed: timestamp or sender mismatch")
                            continue
                            
                        print(f"[{utils.get_timestamp()}] Received broadcast message from Doctor {sender_id}")
                        print(f"[{utils.get_timestamp()}] Decrypted message: {actual_message}")
                        print("OPCODE 50 : DEC MSG")
                
                elif opcode == "60": 
                    print("OPCODE 60 : DISCONNECT")
                    break
                    
                else:
                    print(f"[{utils.get_timestamp()}] Unknown opcode received: {opcode}")
                
            except (ConnectionResetError, ConnectionAbortedError):
                print(f"[{utils.get_timestamp()}] Connection lost with doctor")
                break
            except Exception as e:
                print(f"[{utils.get_timestamp()}] Error receiving message: {e}")
                
    except Exception as e:
        print(f"[{utils.get_timestamp()}] Error in message receiver: {e}")
    finally:
        print(f"[{utils.get_timestamp()}] Message receiver thread ending")
        os._exit(0)

def main(patient_id, doctor_id):
    try:
        patient_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        patient_socket.connect((SERVER_HOST, SERVER_PORT))
        print(f"[{utils.get_timestamp()}] Connected to doctor server at {SERVER_HOST}:{SERVER_PORT}")
        
        doctor_data = patient_socket.recv(4096).decode()
        p_doctor, g_doctor, y_doctor = map(int, doctor_data.split(","))
        
        patient_public_key, patient_private_key = generate_elgamal_keys()
        p, g, y = patient_public_key

        patient_socket.send(f"{p},{g},{y},{patient_id}".encode())
        
        doctor_public_key = (p_doctor, g_doctor, y_doctor)

        auth_request, K_di_gwn = generate_authMessage(patient_private_key, doctor_public_key, patient_id, doctor_id, patient_public_key)
    
        auth_msg = f"10,{auth_request['TS_i']},{auth_request['RN_i']},{auth_request['ID_GWN']},{auth_request['encrypted_key'][0]},{auth_request['encrypted_key'][1]},{auth_request['signature'][0]},{auth_request['signature'][1]}"
        patient_socket.send(auth_msg.encode())
         
        auth_response = patient_socket.recv(4096).decode() #At this point session key has been exchanged.
        
        if auth_response == "FAILED": 
            print("OPCODE 10 : KEY_VERIFICATION (FAILED)")
            patient_socket.close()
            return
            
        response_parts = auth_response.split(',')
        opcode = response_parts[0]
        if opcode == "10":
            TS_GWN = int(response_parts[1])
            RN_GWN = int(response_parts[2])
            id_received = int(response_parts[3])
            enc_key_c1 = int(response_parts[4])
            enc_key_c2 = int(response_parts[5])
            sig_r = int(response_parts[6])
            sig_s = int(response_parts[7])
            
            # Verify timestamp
            current_time = int(time.time())
            if abs(current_time - TS_GWN) > 5:  # 5 seconds tolerance
                print(f"[{utils.get_timestamp()}] Timestamp verification failed")
                patient_socket.close()
                return
                
            # Verify patient ID
            if id_received != patient_id:
                print(f"[{utils.get_timestamp()}] ID verification failed. Expected: {patient_id}, Got: {id_received}")
                patient_socket.close()
                return
                
            # Verify signature
            signature = (sig_r, sig_s)
            data_to_verify = f"{TS_GWN},{RN_GWN},{id_received},{enc_key_c1},{enc_key_c2}"
            
            if verification(data_to_verify, doctor_public_key, signature): 
                print(f"[{utils.get_timestamp()}] Doctor authenticated successfully")
            else:
                print(f"[{utils.get_timestamp()}] Doctor signature verification failed")
                patient_socket.close()
                return
                
            # Decrypt session key
            encrypted_key = (enc_key_c1, enc_key_c2)
            decrypted_key = decrypt_session_key(encrypted_key, patient_private_key, p)
            print(f"[{utils.get_timestamp()}] Decrypted session key from doctor: {decrypted_key}")
            
            # Verify decrypted key matches K_di_gwn ? This is not written in the doc !!
            if decrypted_key == K_di_gwn: 
                print(f"[{utils.get_timestamp()}] Session key verification successful") # Is this where they verify?
                print("OPCODE 10 : KEY_VERIFICATION (SUCCESS)")
            else:
                print("OPCODE 10 : KEY_VERIFICATION (FAILED)")
                patient_socket.close()
                return
            
            # Calculate shared session key (token)
            TS_i = auth_request['TS_i']
            RN_i = auth_request['RN_i']
            session_key_unhashed = int(hashlib.sha256(f"{K_di_gwn},{TS_i},{TS_GWN},{RN_i},{RN_GWN},{patient_id},{doctor_id}".encode()).hexdigest(), 16)
            
            # Send session key verification
            tsi_new = int(time.time())
            session_key_hashed = int(hashlib.sha256(f"{session_key_unhashed},{tsi_new}".encode()).hexdigest(), 16)
            
            verification_msg = f"20,{session_key_hashed},{tsi_new}"
            patient_socket.send(verification_msg.encode())
            print(f"[{utils.get_timestamp()}] Sent shared session key to verification to doctor")
            print("OPCODE 20 : SESSION_TOKEN (SUCCESS)")
            
            receiver_thread = threading.Thread(
                target=receive_messages, 
                args=(patient_socket, session_key_unhashed, doctor_id, patient_id, doctor_public_key, patient_private_key, p)
            )
            receiver_thread.daemon = True
            receiver_thread.start()
            
            print("\n--- Patient Command Interface ---")
            print("Available commands:")
            print("1: Send disconnect request")
            print("2: Exit client")
            
            while True:
                try:
                    command = input("\nEnter command: ")
                    
                    if command == "1":
                        patient_socket.send("60".encode())
                        print(f"[{utils.get_timestamp()}] Sent disconnect request to doctor")
                        break
                        
                    elif command == "2":
                        print(f"[{utils.get_timestamp()}] Exiting client...")
                        patient_socket.close()
                        break
                        
                    else:
                        print("Invalid command")
                        
                except Exception as e:
                    print(f"Error processing command: {e}")
                    break
        else:
            print(f"[{utils.get_timestamp()}] Invalid opcode in authentication response. Expected: 10, Got: {opcode}")
            patient_socket.close()
            
    except Exception as e:
        print(f"[{utils.get_timestamp()}] Error in main patient thread: {e}")
    finally:
        try:
            patient_socket.close()
        except:
            pass
        print(f"[{utils.get_timestamp()}] Patient client terminated")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=int, default=101)
    parser.add_argument('--doctor_id', type=str, default="1")
    
    args = parser.parse_args()
    
    main(args.id, args.doctor_id)