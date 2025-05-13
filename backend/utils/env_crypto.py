from cryptography.fernet import Fernet
import base64
import os
from getpass import getpass

def generate_key(password):
    key = base64.urlsafe_b64encode(password.ljust(32, b'0')[:32])
    return Fernet(key)

def encrypt_env():
    password = getpass("Enter encryption password: ")
    fernet = generate_key(password.encode())
    
    with open('.env', 'rb') as file:
        env_data = file.read()
    
    encrypted_data = fernet.encrypt(env_data)
    
    with open('.env.encrypted', 'wb') as file:
        file.write(encrypted_data)
    
    print(".env file encrypted successfully!")

def read_env():
    password = getpass("Enter decryption password: ")  # Always ask for password
    fernet = generate_key(password.encode())
    
    with open('.env.encrypted', 'rb') as file:  # Read from encrypted file
        encrypted_data = file.read()
    
    try:
        decrypted_data = fernet.decrypt(encrypted_data)
        env_vars = {}
        for line in decrypted_data.decode().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
        return env_vars
    except Exception:
        return {}

def decrypt_env():
    if not os.path.exists('.env.encrypted'):
        print("No encrypted .env file found!")
        return
    
    # Get password from environment variable for Docker
    password = getpass("Enter decryption password: ")
    fernet = generate_key(password.encode())
    
    try:
        with open('.env.encrypted', 'rb') as file:
            encrypted_data = file.read()
        
        decrypted_data = fernet.decrypt(encrypted_data)
        
        with open('.env', 'wb') as file:
            file.write(decrypted_data)
        
        print(".env file decrypted successfully!")
    except Exception as e:
        print(f"Decryption failed: {str(e)}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python env_crypto.py [encrypt|decrypt]")
        sys.exit(1)
    
    if sys.argv[1] == "encrypt":
        encrypt_env()
    elif sys.argv[1] == "decrypt":
        decrypt_env()
