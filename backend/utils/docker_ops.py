import os
from getpass import getpass
from env_crypto import read_env, decrypt_env

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python docker_ops.py [up|down|restart]")
        sys.exit(1)

    # Decrypt the .env file first
    decrypt_env()  # This will prompt for password
    
    command = sys.argv[1]
    if command == "up":
        os.system("docker-compose -f docker-compose.prod.yaml up -d")
    elif command == "down":
        os.system("docker-compose -f docker-compose.prod.yaml down")
    elif command == "restart":
        os.system("docker-compose -f docker-compose.prod.yaml down")
        os.system("docker-compose -f docker-compose.prod.yaml up -d")
    
    # Clean up the decrypted file after docker-compose
    if os.path.exists('.env'):
        os.remove('.env')