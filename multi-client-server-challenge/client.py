import socket
import os

CHUNK_SIZE = 4096
SERVER_IP = "127.0.0.1"
SERVER_PORT = 5000

def send_file(client_socket, file_path):
    """Send a file to the server efficiently."""
    if not os.path.exists(file_path):
        print(f"[-] Error: File '{file_path}' does not exist.")
        return

    filename = os.path.basename(file_path)
    client_socket.sendall(f"UPLOAD {filename}".encode())

    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            client_socket.sendall(chunk)

    client_socket.sendall(b"EOF")  # Mark file end

    response = client_socket.recv(64).decode()
    if response == "UPLOAD_SUCCESS":
        print(f"[✔] File '{filename}' uploaded successfully!")

def retrieve_file(client_socket, filename):
    """Retrieve a file from the server."""
    client_socket.sendall(f"RETRIEVE {filename}".encode())

    received_file = f"retrieved_{filename}"
    with open(received_file, "wb") as f:
        while True:
            chunk = client_socket.recv(CHUNK_SIZE)
            if chunk.endswith(b"EOF"):
                f.write(chunk[:-3])  # Remove "EOF" marker
                break
            f.write(chunk)

    print(f"[✔] File '{received_file}' downloaded successfully!")

def main():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((SERVER_IP, SERVER_PORT))

    while True:
        action = input("\nChoose an action: (upload/retrieve/close) ").strip().lower()

        if action == "upload":
            file_path = input("Enter the file path to upload: ").strip()
            send_file(client_socket, file_path)

        elif action == "retrieve":
            filename = input("Enter the filename to retrieve: ").strip()
            retrieve_file(client_socket, filename)

        elif action == "close":
            client_socket.sendall("CLOSE".encode())
            print("[✔] Connection closed.")
            break

        else:
            print("[-] Invalid command. Try again.")

    client_socket.close()

if __name__ == "__main__":
    main()
