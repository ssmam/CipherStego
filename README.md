# CryptoStego Transit 

CryptoStego Transit is a Python-based GUI application that enables **secure file transfer** by combining **AES-256-GCM encryption** with **steganography** using Image, Text, Audio, or Video files as cover media.

---

## System Requirements

* **Python:** 3.9 or higher
* **Operating System:** Windows / Linux / macOS

---

## Python Dependencies

Create a file named `requirements.txt` with the following content:

```txt
cryptography>=41.0.0
opencv-python>=4.8.0
Pillow>=10.0.0
pygame>=2.5.0
```

Install dependencies using:

```bash
pip install -r requirements.txt
```

> Note:
>
> * Image & Video steganography require `opencv-python`
> * Image preview requires `Pillow`
> * Audio preview requires `pygame`

---

## How to Run

1. Clone the repository:

```bash
git clone https://github.com/ssmam/CipherStego.git
cd CryptoStego-Transit
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the application:

```bash
python main.py
```

The graphical interface will launch automatically.

---

## Usage Guide

### Sender

1. Open the **Sender** tab
2. Enter the receiver **IP address** and **port**
3. Set a **strong passphrase** (minimum 12 characters)
4. Select:

   * A **secret file** (file to be protected)
   * A **cover file** (image / text / audio / video)
5. Choose the steganography method
6. Click **SEND STEGO PAYLOAD**

The file will be encrypted, embedded into the cover file, and sent over TCP.

---

### Receiver

1. Open the **Receiver** tab
2. Enter the listening **port**
3. Enter the **same passphrase** used by the sender
4. Set an output directory (default: `./received`)
5. Click **LISTEN FOR STEGO FILE**
6. After receiving the file, click **DECRYPT**

The decrypted file will be saved as:

```text
received/DECRYPTED_SECRET.bin
```

---

## Password Policy

Passwords must contain:

* At least **12 characters**
* One **uppercase letter**
* One **lowercase letter**
* One **number**
* One **special character** (`!@#$%^&*`)

Weak passwords are rejected by the application.

---

## Notes

* Sender and Receiver must use the **same passphrase**
* Larger secret files require larger cover files
* This tool is not designed for real-world covert operations

---

## License

This tool is intended for **educational and cybersecurity project use**.
