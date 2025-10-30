#!/bin/bash
set -e

OPENSSL_VERSION="3.5.4"
INSTALL_PREFIX="/usr/local/ssl"
SRC_DIR="/usr/local/src"
TARBALL="openssl-${OPENSSL_VERSION}.tar.gz"
URL="https://www.openssl.org/source/${TARBALL}"

echo "=== OpenSSL auto-update script ==="
echo "Target version: ${OPENSSL_VERSION}"
echo "Install prefix: ${INSTALL_PREFIX}"
echo

# 1. Проверяем текущую версию
echo "Current system OpenSSL version:"
openssl version
echo

# 2. Подготавливаем директории
sudo mkdir -p ${SRC_DIR}
cd ${SRC_DIR}

# 3. Скачиваем исходники
if [ ! -f "${TARBALL}" ]; then
    echo "Downloading OpenSSL ${OPENSSL_VERSION}..."
    sudo wget -q ${URL} -O ${TARBALL}
else
    echo "Source archive already exists, skipping download."
fi

# 4. Распаковываем и собираем
sudo rm -rf "openssl-${OPENSSL_VERSION}"
sudo tar xzf ${TARBALL}
cd "openssl-${OPENSSL_VERSION}"

echo "Configuring OpenSSL..."
sudo ./Configure \
    --prefix=${INSTALL_PREFIX} \
    --openssldir=${INSTALL_PREFIX} \
    enable-ec_nistp_64_gcc_128 \
    shared zlib

echo "Building OpenSSL (this may take a few minutes)..."
sudo make -j$(nproc)

echo "Installing to ${INSTALL_PREFIX}..."
sudo make install_sw

# 5. Настраиваем системные пути
if ! grep -q "${INSTALL_PREFIX}/lib" /etc/ld.so.conf.d/openssl-${OPENSSL_VERSION}.conf 2>/dev/null; then
    echo "${INSTALL_PREFIX}/lib" | sudo tee /etc/ld.so.conf.d/openssl-${OPENSSL_VERSION}.conf > /dev/null
fi
sudo ldconfig

# 6. Обновляем PATH временно и для будущих сессий
if ! grep -q "${INSTALL_PREFIX}/bin" /etc/profile.d/openssl.sh 2>/dev/null; then
    echo "export PATH=${INSTALL_PREFIX}/bin:\$PATH" | sudo tee /etc/profile.d/openssl.sh > /dev/null
fi
export PATH=${INSTALL_PREFIX}/bin:$PATH

# 7. Проверяем версию
echo
echo "=== Installed OpenSSL version ==="
${INSTALL_PREFIX}/bin/openssl version
echo

# 8. Проверка, что новая версия используется по умолчанию
echo "To make it default in the current session, run:"
echo "  export PATH=${INSTALL_PREFIX}/bin:\$PATH"
echo
echo "To verify globally after reboot:"
echo "  openssl version"
echo
echo "✅ OpenSSL ${OPENSSL_VERSION} successfully installed to ${INSTALL_PREFIX}"
