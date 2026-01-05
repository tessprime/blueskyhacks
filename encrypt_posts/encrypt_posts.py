from Crypto.Util.Padding import pad, unpad
from Crypto.Util.number import bytes_to_long, long_to_bytes, getPrime
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from Crypto.Cipher import AES, PKCS1_OAEP
import base64
import json

import argparse

exponent = 2**16+1

# look, just don't use this code for anything beyond recreational shit posting.
def encrypt_post_badly(post_content, public_key_json):
    # Generate a random AES key
    aes_key = get_random_bytes(16)  # AES-128

    # Encrypt the post content using AES
    cipher_aes = AES.new(aes_key, AES.MODE_CBC)
    iv = cipher_aes.iv
    encrypted_content = cipher_aes.encrypt(pad(post_content.encode('utf-8'), AES.block_size))

    # Encrypt the AES key using RSA
    public_key = RSA.RsaKey(n=public_key_json['n'], e=public_key_json['e'])
    #cipher_rsa = PKCS1_OAEP.new(public_key)
    encrypted_aes_key = long_to_bytes(pow(bytes_to_long(aes_key), public_key.e, public_key.n))

    # Encode everything in base64 for easy storage/transmission
    encrypted_post = {
        'n': public_key_json['n'],
        'e': public_key_json['e'],
        'encrypted_aes_key': base64.b64encode(encrypted_aes_key).decode('utf-8'),
        'iv': base64.b64encode(iv).decode('utf-8'),
        'encrypted_content': base64.b64encode(encrypted_content).decode('utf-8')
    }
    return encrypted_post

def decrypt_post(encrypted_post, private_key):
    # Decode base64 encoded fields
    encrypted_aes_key = base64.b64decode(encrypted_post['encrypted_aes_key'])
    print(bytes_to_long(encrypted_aes_key))
    iv = base64.b64decode(encrypted_post['iv'])
    encrypted_content = base64.b64decode(encrypted_post['encrypted_content'])

    #cipher_rsa = PKCS1_OAEP.new(private_key)
    print("ekey", bytes_to_long(encrypted_aes_key) )
    aes_key = long_to_bytes(pow(bytes_to_long(encrypted_aes_key), private_key.d, private_key.n))
    print("dkey", bytes_to_long(aes_key))

    # Decrypt the post content using AES
    cipher_aes = AES.new(aes_key, AES.MODE_CBC, iv)
    decrypted_content = unpad(cipher_aes.decrypt(encrypted_content), AES.block_size)

    return decrypted_content.decode('utf-8')

def minimal_key_json():
    while True:
        try:
            p, q = getPrime(128), getPrime(128)
            d = pow(exponent, -1, (p-1)*(q-1))
            print("n",p*q, "d", d)
            return {
                'n': p * q,
                'e': exponent
            }, RSA.RsaKey(n=p*q, e=exponent, d=d, p=p, q=q, u=pow(q, -1, p))
        except ValueError as e:
            #print("Error generating keys:", e)
            continue

def main():
    parser = argparse.ArgumentParser(description="Encrypt and decrypt posts using hybrid RSA-AES encryption.")
    parser.add_argument('--post', type=str, help="The post content to encrypt.")
    parser.add_argument('--post-file', type=str, help="File to read post content from.")
    options = parser.parse_args()

    if options.post:
        post_content = options.post
    elif options.post_file:
        with open(options.post_file, 'r') as f:
            post_content = f.read()
    else:
        parser.print_help()
        return

    public_key_json, private_key = minimal_key_json()
    encrypted_post = encrypt_post_badly(post_content, public_key_json)
    print("Encrypted post:", encrypted_post)

    # validate
    decrypted_content = decrypt_post(encrypted_post, private_key)
    print("Decrypted post:", decrypted_content)

    i = 0
    encrypt_post_b64 = base64.b64encode(json.dumps(encrypted_post).encode())
    while i*300 < len(encrypt_post_b64):
        chunk = encrypt_post_b64[i*300:i*300+300]
        print(chunk.decode())
        i += 1

if __name__ == "__main__":
    main()
