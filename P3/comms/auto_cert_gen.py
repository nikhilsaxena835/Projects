from OpenSSL import crypto
import os

def create_ca():
    # Generate CA key
    ca_key = crypto.PKey()
    ca_key.generate_key(crypto.TYPE_RSA, 2048)
    
    # Generate CA certificate
    ca_cert = crypto.X509()
    ca_subject = ca_cert.get_subject()
    ca_subject.C = "IN"
    ca_subject.ST = "MP"
    ca_subject.L = "HYD"
    ca_subject.O = "IIITH"
    ca_subject.OU = "DS"
    ca_subject.CN = "STRIFE_CA"  # Clearly indicate this is the CA
    
    ca_cert.set_serial_number(1000)
    ca_cert.gmtime_adj_notBefore(0)
    ca_cert.gmtime_adj_notAfter(365*24*60*60)
    ca_cert.set_issuer(ca_subject)
    ca_cert.set_pubkey(ca_key)
    ca_cert.sign(ca_key, 'sha256')
    
    return ca_cert, ca_key

def generate_signed_cert(cert_dir, name, cn, ca_cert, ca_key, serial):
    # Generate key for the certificate
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)
    
    # Generate certificate
    cert = crypto.X509()
    cert_subject = cert.get_subject()
    cert_subject.C = "IN"
    cert_subject.ST = "MP"
    cert_subject.L = "HYD"
    cert_subject.O = "IIITH"
    cert_subject.OU = "DS"
    cert_subject.CN = cn  # Use provided common name

    cert.set_serial_number(serial)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365*24*60*60)
    cert.set_issuer(ca_cert.get_subject())
    cert.set_pubkey(key)
    
    # Add Subject Alternative Name extension (example for localhost)
    san_list = [b"DNS:localhost", b"IP:127.0.0.1"]
    san_extension = crypto.X509Extension(b"subjectAltName", False, b", ".join(san_list))
    cert.add_extensions([san_extension])
    
    # Optionally, add Extended Key Usage (serverAuth/clientAuth)
    eku = crypto.X509Extension(b"extendedKeyUsage", False, b"serverAuth, clientAuth")
    cert.add_extensions([eku])
    
    # Sign certificate with CA
    cert.sign(ca_key, 'sha256')
    
    # Save certificate and private key
    if not os.path.exists(cert_dir):
        os.makedirs(cert_dir)
        
    cert_path = os.path.join(cert_dir, f"{name}.crt")
    key_path = os.path.join(cert_dir, f"{name}.key")
    with open(cert_path, "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    with open(key_path, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
        
    return cert, key

if __name__ == "__main__":
    cert_dir = "certs"
    
    # Create CA
    ca_cert, ca_key = create_ca()
    
    # Save CA certificate
    with open(os.path.join(cert_dir, "ca.crt"), "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert))
    
    # Generate signed certificates for each component with unique serial numbers
    generate_signed_cert(cert_dir, "gateway", "gateway", ca_cert, ca_key, serial=1001)
    generate_signed_cert(cert_dir, "bank", "bank", ca_cert, ca_key, serial=1002)
    generate_signed_cert(cert_dir, "client", "client", ca_cert, ca_key, serial=1003)
