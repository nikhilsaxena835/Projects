import base64
import socket
import threading
import random
import os
import time
import hashlib
import argparse
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad
import utils

HOST = '127.0.0.1'
PORT = 9000
TIMESTAMP_TOLERANCE = 5

patient_session_keys = {}
active_patients = {}
patients_lock = threading.Lock()

def generate_elgamal_keys():
    p, g = utils.get_prime_and_generator()
    x = random.randint(2, p - 2) 
    y = pow(g, x, p) 
    return (p, g, y), x  # Public key tuple (p, g, y) and private key x


def encrypt_session_key(msg, patient_public_key):
    p, g, y = patient_public_key
    if isinstance(msg, bytes):
        msg = int.from_bytes(msg, byteorder='big')
    
    # Choose a random ephemeral key. 1 and p-1 are edge cases and guessed first. So excluding them.
    k = random.randint(2, p - 2)
    
    c1 = pow(g, k, p)
    c2 = (msg * pow(y, k, p)) % p
    
    return c1, c2

def decrypt_session_key(cipher_msg, private_key, p):
    c1, c2 = cipher_msg
    s = pow(c1, private_key, p)
    s_inv = pow(s, p - 2, p)
    session_key = (c2 * s_inv) % p
    
    return session_key

def sign_data(data, private_key, public_key):
    p, g, y = public_key
    hash_value = int(hashlib.sha256(data.encode()).hexdigest(), 16) % (p-1)
    k = utils.find_coprime(p-1)   # Choose a random k that is coprime to p-1
    r = pow(g, k, p)
    k_inv = pow(k, -1, p-1)
    s = (k_inv * (hash_value - private_key * r) % (p-1)) % (p-1)
    
    return (r, s)

def verification(dataToVerify, public_key, sgndata):
    p, g, y = public_key
    sig_r, sig_s = sgndata
    
    # Check if r and s is in the valid range
    if not (1 <= sig_r < p or 1 <= sig_s < p-1):
        return False
    
    hash_value = int(hashlib.sha256(dataToVerify.encode()).hexdigest(), 16) % (p-1)
    left_side = pow(g, hash_value, p)
    right_side = (pow(y, sig_r, p) * pow(sig_r, sig_s, p)) % p
    
    return left_side == right_side

@utils.measure_time(label="AES Encryption")
def encrypt_with_aes(data, key):
    if isinstance(key, int):
        key_bytes = key.to_bytes(32, byteorder='big')
    elif isinstance(key, str):
        key_bytes = hashlib.sha256(key.encode()).digest()
    else:
        key_bytes = key
        
    if isinstance(data, str):
        data_bytes = data.encode()
    elif isinstance(data, int):
        data_bytes = str(data).encode()
    else:
        data_bytes = data
        
    iv = os.urandom(16)
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    
    padded_data = pad(data_bytes, AES.block_size)
    encrypted_data = cipher.encrypt(padded_data)
    
    encrypted_payload = base64.b64encode(iv + encrypted_data).decode('utf-8')
    return encrypted_payload, iv

def generate_group_key(doctor_private_key):
    with patients_lock:
        if not patient_session_keys:
            return None
        
        keys_str = ""
        for patient_id, session_key in patient_session_keys.items():
            keys_str += str(session_key)
        
        keys_str += str(doctor_private_key)
        group_key = int(hashlib.sha256(keys_str.encode()).hexdigest(), 16)
        return group_key

def remove_disconnected(patients_to_remove):
    for patient_id in patients_to_remove:
            if patient_id in active_patients:
                try:
                    active_patients[patient_id]["socket"].close()
                except:
                    pass
                del active_patients[patient_id]
            if patient_id in patient_session_keys:
                del patient_session_keys[patient_id]
            print(f"[{utils.get_timestamp()}] Removed disconnected patient {patient_id}")

def broadcast_group_key(group_key, doctor_id):
    with patients_lock:
        patients_to_remove = []
        for patient_id, patient_info in active_patients.items():
            patient_socket = patient_info["socket"]
            session_key = patient_session_keys[patient_id]
            
            try:
                encrypted_payload, _ = encrypt_with_aes(str(group_key), session_key)
                ts = int(time.time())
                message = f"30,{encrypted_payload},{ts},{doctor_id}"
                patient_socket.send(message.encode())
                print(f"[{utils.get_timestamp()}] Sent encrypted group key to patient {patient_id}")
            except Exception as e:
                print(f"[{utils.get_timestamp()}] Error sending group key to patient {patient_id}: {e}")
                patients_to_remove.append(patient_id)
        
        remove_disconnected(patients_to_remove)
        

def broadcast_message(message, group_key, doctor_id):
    ts = int(time.time())
    message_with_ts = f"{ts},{doctor_id},{message}"

    encrypted_payload, _ = encrypt_with_aes(message_with_ts, group_key)
    broadcast_msg = f"40,{encrypted_payload},{ts},{doctor_id}"
    
    with patients_lock:
        patients_to_remove = []
        for patient_id, patient_info in active_patients.items():
            patient_socket = patient_info["socket"]
            try:
                patient_socket.send(broadcast_msg.encode())
                print(f"[{utils.get_timestamp()}] Broadcasted encrypted message to patient {patient_id}")
            except Exception as e:
                print(f"[{utils.get_timestamp()}] Error broadcasting to patient {patient_id}: {e}")
                patients_to_remove.append(patient_id)

        remove_disconnected(patients_to_remove)


def disconnect_all_patients():
    with patients_lock:
        for patient_id, patient_info in active_patients.items():
            patient_socket = patient_info["socket"]
            try:
                patient_socket.send("60".encode())
                patient_socket.close()
                print(f"[{utils.get_timestamp()}] Disconnected patient {patient_id}")
            except Exception as e:
                print(f"[{utils.get_timestamp()}] Error disconnecting patient {patient_id}: {e}")
        
        active_patients.clear()
        patient_session_keys.clear()

def handle_patient(patient_socket, addr, doctor_public_key, doctor_private_key, doctor_id):
    patient_id = None
    patient_public_key = None
    
    try:
        print(f"[{utils.get_timestamp()}] Connected to patient at {addr}")
        
        p_doctor, g_doctor, y_doctor = doctor_public_key
        patient_socket.send(f"{p_doctor},{g_doctor},{y_doctor}".encode())
        
        patient_data = patient_socket.recv(4096).decode() #Do I need this 4096 B limit ?
        p_patient, g_patient, y_patient, patient_id = map(int, patient_data.split(","))
        patient_public_key = (p_patient, g_patient, y_patient)
        
        auth_req = patient_socket.recv(4096).decode()
        auth_split = auth_req.split(',')
        opcode = auth_split[0]

        if(opcode == "10"): 
            TS_i = int(auth_split[1])
            RN_i = int(auth_split[2])
            ID_GWN = auth_split[3]
            enc_key_c1 = int(auth_split[4])
            enc_key_c2 = int(auth_split[5])
            sig_r = int(auth_split[6])
            sig_s = int(auth_split[7])

            if(ID_GWN != doctor_id):
                print(f"Fake patient. Expected id: {doctor_id}, Got {ID_GWN}")
                patient_socket.send("FAILED".encode())
                return
            
            current_time = int(time.time())
            if abs(current_time - TS_i) > TIMESTAMP_TOLERANCE:  
                print(f"[{utils.get_timestamp()}] Timestamp verification failed")
                patient_socket.send("FAILED".encode())
                return
                
            signature = (sig_r, sig_s) 
            data_to_verify = f"{TS_i},{RN_i},{ID_GWN},{enc_key_c1},{enc_key_c2}"

            if verification(data_to_verify, patient_public_key, signature):# This is where I verify the signed data from patient.
                print(f"[{utils.get_timestamp()}] Patient {patient_id} authenticated successfully")
            else:
                print(f"[{utils.get_timestamp()}] Bad patient - Signature verification failed")
                patient_socket.send("FAILED".encode())
                return
            
            encrypted_key = (enc_key_c1, enc_key_c2)
            K_Di_GWN = decrypt_session_key(encrypted_key, doctor_private_key, p_doctor)
            print(f"[{utils.get_timestamp()}] Decrypted session key from patient: {K_Di_GWN}")

            TS_GWN = int(time.time())
            RN_GWN = random.randint(1, 2**64)
            id = patient_id  

            re_encrypted_key = encrypt_session_key(K_Di_GWN, patient_public_key)

            data_to_sign = f"{TS_GWN},{RN_GWN},{id},{re_encrypted_key[0]},{re_encrypted_key[1]}"
            doctor_signature = sign_data(data_to_sign, doctor_private_key, doctor_public_key)
            
            response = f"10,{TS_GWN},{RN_GWN},{id},{re_encrypted_key[0]},{re_encrypted_key[1]},{doctor_signature[0]},{doctor_signature[1]}"
            patient_socket.send(response.encode())
            print(f"[{utils.get_timestamp()}] Sent authentication response to patient {patient_id}")
            print("OPCODE 10 : KEY_VERIFICATION (SUCCESS")
            verification_msg = patient_socket.recv(4096).decode()
            verification_parts = verification_msg.split(',')

            if verification_parts[0] == "20":
                session_key_recv = int(verification_parts[1])
                tsi_new = int(verification_parts[2])

                current_time = int(time.time())
                if abs(current_time - tsi_new) > 5:  # 5 seconds tolerance
                    print(f"[{utils.get_timestamp()}] Timestamp verification failed for session key verification")
                    return

                session_key_unhashed = int(hashlib.sha256(f"{K_Di_GWN},{TS_i},{TS_GWN},{RN_i},{RN_GWN},{patient_id},{doctor_id}".encode()).hexdigest(), 16)
                session_key_hashed = int(hashlib.sha256(f"{session_key_unhashed},{tsi_new}".encode()).hexdigest(), 16)  

                if session_key_hashed == session_key_recv:
                    print(f"[{utils.get_timestamp()}] Session key verification successful for patient {patient_id}")
                    print("OPCODE 20 : SESSION_TOKEN") #YES ! THIS IS CORRECT
                    
                    with patients_lock:
                        patient_session_keys[patient_id] = session_key_unhashed
                        active_patients[patient_id] = {
                            "socket": patient_socket, 
                            "public_key": patient_public_key,
                            "addr": addr
                        }
                        
                    print(f"[{utils.get_timestamp()}] Patient {patient_id} added to the system")
                else:
                    print(f"[{utils.get_timestamp()}] Bad Patient {patient_id} -- session key not matched")
                    return
            else:
                print(f"[{utils.get_timestamp()}] Invalid Opcode. Expected: 20. Got: {verification_parts[0]}")
        else:
            print(f"[{utils.get_timestamp()}] Invalid Opcode. Expected: 10. Got: {opcode}")
            return
            
        while True:
            try:
                data = patient_socket.recv(4096).decode()
                if not data:
                    break
                    
                parts = data.split(',')
                opcode = parts[0]
                
                if opcode == "60":  # DISCONNECT
                    print(f"[{utils.get_timestamp()}] Patient {patient_id} requested disconnect")
                    break
                    
                
            except (ConnectionResetError, ConnectionAbortedError):
                print(f"[{utils.get_timestamp()}] Connection with patient {patient_id} lost")
                break
            except Exception as e:
                print(f"[{utils.get_timestamp()}] Error in patient {patient_id} communication: {e}")
                break
                
    except Exception as e:
        print(f"[{utils.get_timestamp()}] Error handling patient at {addr}: {e}")
    
    finally:
        if patient_id:
            with patients_lock:
                if patient_id in active_patients:
                    del active_patients[patient_id]
                if patient_id in patient_session_keys:
                    del patient_session_keys[patient_id]
                    
        try:
            patient_socket.close()
        except:
            pass
            
        print(f"[{utils.get_timestamp()}] Connection with patient {patient_id if patient_id else addr} closed")

def start_doctor_server(doctor_id):
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    print(f"[{utils.get_timestamp()}] Doctor server started at {HOST}:{PORT}")

    with utils.Timer(label="El Gamal Key Generation"):
        doctor_public_key, doctor_private_key = generate_elgamal_keys()
        
    doctor_thread = threading.Thread(target=doctor_command_handler, args=(doctor_public_key, doctor_private_key, doctor_id))
    doctor_thread.daemon = True 
    doctor_thread.start()

    try:
        while True:
            patient_socket, addr = server_socket.accept()
            threading.Thread(
                target=handle_patient, 
                args=(patient_socket, addr, doctor_public_key, doctor_private_key, doctor_id)
            ).start()
    except KeyboardInterrupt:
        print(f"[{utils.get_timestamp()}] Server shutting down...")
    finally:
        disconnect_all_patients()
        server_socket.close()

def doctor_command_handler(doctor_public_key, doctor_private_key, doctor_id):    
    while True:
        try:
            print("\n--- Doctor Command Interface ---")
            print("1: List connected patients")
            print("2: Broadcast message to all patients")
            print("3: Disconnect all patients")
            print("4: Exit server")
            command = input("\nEnter command: ")
            
            if command == "1":
                with patients_lock:
                    if not active_patients:
                        print("No patients connected")
                    else:
                        print(f"Connected patients ({len(active_patients)}):")
                        for patient_id in active_patients:
                            print(f"- Patient ID: {patient_id}")

            elif command == "2":
                message = input("Enter message to broadcast: ")
                with utils.Timer("Broadcast Message"):   
                    with patients_lock:
                        if not active_patients:
                            print("No patients connected. Cannot broadcast message.")
                            continue
                    
                    
                    
                    group_key = generate_group_key(doctor_private_key)
                    if not group_key:
                        print("Failed to generate group key for broadcast")
                        continue
                    
                
                    broadcast_group_key(group_key, doctor_id)
                    
                    broadcast_message(message, group_key, doctor_id)
                    print("OPCODE 40 : ENC_MSG")
                    print(f"Message broadcasted to {len(active_patients)} patients")
            
            elif command == "3":  
                disconnect_all_patients()
                print("All patients disconnected")
            
            elif command == "4":  
                print("Exiting server...")
                disconnect_all_patients()
                os._exit(0) 
            
            else:
                print("Invalid command")
                
        except Exception as e:
            print(f"Error processing command: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=str, default="1")
    args = parser.parse_args()

    doctor_id = args.id

    start_doctor_server(doctor_id)