#!/usr/bin/env bash
set -euo pipefail

# gen_certs.sh
# Генератор сертификатов с CA, поддержкой GOST и EC, PFX и CRL
# Пример запуска:
# ./openssl_gen_certs.sh --dir ./out --name TestClient --paramset TCA --org "MyOrg" --ca-cn "MyCA" --days 825

print_help() {
cat <<'EOF'
Usage: openssl_gen_certs.sh [options]

Options:
  --dir DIR                 Directory for storing data (default: ./out)
  --name NAME               Object name (used in CN and filenames) (default: TestObject)
  --paramset SET            Parameter set (e.g. TCA, TCB, TCC, TCD, A, B, C, SECP256R1, SECP384R1, SECP521R1)
  --encrypt-keys true|false Encrypt private keys (default: true)
  --encrypt-pfx  true|false Encrypt PFX (default: true)
  --key-pass PASSWORD       Password for private key encryption (default: pass1234)
  --pfx-pass PASSWORD       Password for PFX (default: pass1234)
  --org ORG                 Organization name for certs (default: MyOrg)
  --ca-cn CA_CN             CommonName for CA (default: MyCA)
  --days DAYS               Lifetime in days for issued certs (default: 825)
  --selfsign true|false     Generate self-signed certificate (default: false)
  --keep-ca                 Do not remove CA directory at the end (default: false)
  --help                    Show this help and exit
EOF
}

# -------------------------
# Defaults
# -------------------------
BASE_DIR="./out"
OBJ_NAME="TestObject"
PARAMSET="TCA"
ENCRYPT_KEYS="true"
ENCRYPT_PFX="true"
KEY_PASS="pass1234"
PFX_PASS="pass1234"
ORG_NAME="MyOrg"
CA_CN="MyCA"
DAYS=825
SELFSIGN="false"
KEEP_CA="false"

# -------------------------
# Parse long options
# -------------------------
if ! GETOPT_BIN=$(command -v getopt); then
    echo "Error: getopt not found" >&2
    exit 1
fi

OPTIONS=\
"dir:,name:,paramset:,encrypt-keys:,encrypt-pfx:,key-pass:,pfx-pass:,org:,ca-cn:,days:,selfsign:,keep-ca,help"

PARSED=$($GETOPT_BIN -o '' --long "$OPTIONS" -- "$@") || { print_help; exit 2; }
eval set -- "$PARSED"

while true; do
    case "$1" in
        --dir) BASE_DIR="$2"; shift 2 ;;
        --name) OBJ_NAME="$2"; shift 2 ;;
        --paramset) PARAMSET="$2"; shift 2 ;;
        --encrypt-keys) ENCRYPT_KEYS="$2"; shift 2 ;;
        --encrypt-pfx) ENCRYPT_PFX="$2"; shift 2 ;;
        --key-pass) KEY_PASS="$2"; shift 2 ;;
        --pfx-pass) PFX_PASS="$2"; shift 2 ;;
        --org) ORG_NAME="$2"; shift 2 ;;
        --ca-cn) CA_CN="$2"; shift 2 ;;
        --days) DAYS="$2"; shift 2 ;;
        --selfsign) SELFSIGN="$2"; shift 2 ;;
        --keep-ca) KEEP_CA="true"; shift ;;
        --help) print_help; exit 0 ;;
        --) shift; break ;;
        *) echo "Unknown option: $1"; exit 3 ;;
    esac
done

to_bool() {
    case "${1,,}" in
        1|y|yes|true) echo "true" ;;
        *) echo "false" ;;
    esac
}
ENCRYPT_KEYS=$(to_bool "$ENCRYPT_KEYS")
ENCRYPT_PFX=$(to_bool "$ENCRYPT_PFX")
SELFSIGN=$(to_bool "$SELFSIGN")

# -------------------------
# Determine algorithms by paramset
# -------------------------
SIGNALGO=""
HASHALGO=""
POINTLEN=""
PKEYOPT=""
KEY_ENC_ALGO=""
PFX_KEYPBE=""
PFX_CERTPBE=""
PFX_MACALG=""
USE_GOST_ENGINE="false"

param_upper=$(printf '%s' "$PARAMSET" | tr '[:lower:]' '[:upper:]')

if [[ "$param_upper" =~ ^TC[A-D]$ ]]; then
    SIGNALGO="gost2012_256"
    HASHALGO="md_gost12_256"
    POINTLEN="256"
    PKEYOPT="paramset:$param_upper"
    KEY_ENC_ALGO="gost89"
    PFX_KEYPBE="gost89"
    PFX_CERTPBE="gost89"
    PFX_MACALG="md_gost12_256"
    USE_GOST_ENGINE="true"
elif [[ "$param_upper" =~ ^(A|B|C)$ ]]; then
    SIGNALGO="gost2012_512"
    HASHALGO="md_gost12_512"
    POINTLEN="512"
    PKEYOPT="paramset:$param_upper"
    KEY_ENC_ALGO="gost89"
    PFX_KEYPBE="gost89"
    PFX_CERTPBE="gost89"
    PFX_MACALG="md_gost12_512"
    USE_GOST_ENGINE="true"
elif [[ "$param_upper" == "SECP256R1" ]]; then
    SIGNALGO="ec"
    HASHALGO="sha256"
    POINTLEN="256"
    PKEYOPT="ec_paramgen_curve:prime256v1"
    KEY_ENC_ALGO="aes-256-cbc"
elif [[ "$param_upper" == "SECP384R1" ]]; then
    SIGNALGO="ec"
    HASHALGO="sha384"
    POINTLEN="384"
    PKEYOPT="ec_paramgen_curve:secp384r1"
    KEY_ENC_ALGO="aes-256-cbc"
elif [[ "$param_upper" == "SECP521R1" ]]; then
    SIGNALGO="ec"
    HASHALGO="sha512"
    POINTLEN="521"
    PKEYOPT="ec_paramgen_curve:secp521r1"
    KEY_ENC_ALGO="aes-256-cbc"
else
    echo "Unknown paramset: $PARAMSET" >&2
    exit 1
fi

# -------------------------
# Detect engine
# -------------------------
detect_engine() {
    local use_gost="$1"
    if [[ "$use_gost" == "true" ]]; then
        if openssl engine gost -t &>/dev/null; then
            echo "=> Using GOST engine for OpenSSL operations"
            ENGINE_OPT="-engine gost"
        else
            echo "=> Warning: GOST engine not available, continuing without it"
            ENGINE_OPT=""
        fi
    else
        ENGINE_OPT=""
    fi
}
detect_engine "$USE_GOST_ENGINE"

# -------------------------
# Filenames
# -------------------------
CA_DIR="$BASE_DIR/ca"
CA_KEY_FILENAME="ca_key_${param_upper}.pem"
CA_CERT_FILENAME="ca_cert_${param_upper}.pem"
OBJ_KEY_FILENAME="${OBJ_NAME}_key_${param_upper}.pem"
OBJ_CSR_FILENAME="${OBJ_NAME}_csr_${param_upper}.pem"
OBJ_CERT_FILENAME="${OBJ_NAME}_cert_${param_upper}.pem"
OBJ_PFX_FILENAME="${OBJ_NAME}_pfx_${param_upper}.pfx"
CA_CRL_FILENAME="ca_crl_${param_upper}.pem"

# -------------------------
# Prepare directories
# -------------------------
echo "=> Preparing directories in: $BASE_DIR"
mkdir -p "$CA_DIR"/{certs,csr,newcerts,private,crl}
chmod 700 "$CA_DIR/private"
touch "$CA_DIR/index.txt"
echo 1000 > "$CA_DIR/serial"
echo 1000 > "$CA_DIR/crlnumber"

# -------------------------
# Create OpenSSL config
# -------------------------
OPENSSL_CNF="$CA_DIR/openssl.cnf"
cat > "$OPENSSL_CNF" <<EOF
[ ca ]
default_ca = CA_default

[ CA_default ]
dir               = $CA_DIR
certs             = \$dir/certs
crl_dir           = \$dir/crl
new_certs_dir     = \$dir/newcerts
database          = \$dir/index.txt
serial            = \$dir/serial
crlnumber         = \$dir/crlnumber
RANDFILE          = \$dir/private/.rand

private_key       = \$dir/private/$CA_KEY_FILENAME
certificate       = \$dir/certs/$CA_CERT_FILENAME
crl               = \$dir/crl/$CA_CRL_FILENAME

default_md        = $HASHALGO
default_days      = $DAYS
preserve          = no
email_in_dn       = no
name_opt          = ca_default
cert_opt          = ca_default
copy_extensions   = copy

default_crl_days  = 30

policy            = policy_anything

[ policy_anything ]
commonName             = supplied
organizationName       = optional

[ req ]
default_bits        = 4096
distinguished_name  = req_distinguished_name
string_mask         = utf8only
default_md          = $HASHALGO
prompt              = no

[ req_distinguished_name ]
C  = RU
ST = ExampleRegion
L  = ExampleCity
O  = $ORG_NAME
CN = $OBJ_NAME

[ v3_ca ]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical,CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ v3_req ]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
EOF

# -------------------------
# Generate CA
# -------------------------
echo "=> Generating CA key and certificate..."
openssl genpkey $ENGINE_OPT -algorithm "$SIGNALGO" -pkeyopt "$PKEYOPT" \
    -out "$CA_DIR/private/$CA_KEY_FILENAME"

openssl req $ENGINE_OPT -x509 -new -key "$CA_DIR/private/$CA_KEY_FILENAME" \
    -days "$DAYS" -out "$CA_DIR/certs/$CA_CERT_FILENAME" \
    -config "$OPENSSL_CNF" -extensions v3_ca

# -------------------------
# Generate object key and CSR
# -------------------------
echo "=> Generating object key and CSR..."
openssl genpkey $ENGINE_OPT -algorithm "$SIGNALGO" -pkeyopt "$PKEYOPT" \
    -out "$BASE_DIR/$OBJ_KEY_FILENAME"

openssl req $ENGINE_OPT -new -key "$BASE_DIR/$OBJ_KEY_FILENAME" \
    -out "$BASE_DIR/$OBJ_CSR_FILENAME" -config "$OPENSSL_CNF" -extensions v3_req

# -------------------------
# Sign CSR with CA
# -------------------------
if [[ "$SELFSIGN" == "true" ]]; then
    echo "=> Generating self-signed certificate..."
    openssl req $ENGINE_OPT -x509 -new -key "$BASE_DIR/$OBJ_KEY_FILENAME" \
        -days "$DAYS" -out "$BASE_DIR/$OBJ_CERT_FILENAME" -config "$OPENSSL_CNF"
else
    echo "=> Signing certificate with CA..."
    openssl ca $ENGINE_OPT -batch -config "$OPENSSL_CNF" -in "$BASE_DIR/$OBJ_CSR_FILENAME" \
        -out "$BASE_DIR/$OBJ_CERT_FILENAME" -extensions v3_req -days "$DAYS"
fi

# -------------------------
# Generate CRL
# -------------------------
echo "=> Generating CRL..."
openssl ca $ENGINE_OPT -gencrl -config "$OPENSSL_CNF" -out "$CA_DIR/crl/$CA_CRL_FILENAME"

# -------------------------
# Create PFX
# -------------------------
echo "=> Creating PFX..."
PFX_ENC_ARGS=()
if [[ "$ENCRYPT_PFX" == "true" ]]; then
    PFX_ENC_ARGS=(-passout "pass:$PFX_PASS")
else
    PFX_ENC_ARGS=(-nodes)
fi

openssl pkcs12 $ENGINE_OPT -export -out "$BASE_DIR/$OBJ_PFX_FILENAME" \
    -inkey "$BASE_DIR/$OBJ_KEY_FILENAME" -in "$BASE_DIR/$OBJ_CERT_FILENAME" \
    -certfile "$CA_DIR/certs/$CA_CERT_FILENAME" "${PFX_ENC_ARGS[@]}"

# -------------------------
# Cleanup
# -------------------------
if [[ "$KEEP_CA" != "true" ]]; then
    echo "=> Cleaning CA directory..."
    rm -rf "$CA_DIR"
fi

echo "✅ Done! Certificates and keys generated in: $BASE_DIR"
