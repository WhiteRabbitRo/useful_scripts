#!/bin/bash

# Скрипт для настройки реверсивного USB-тетеринга (шаринг интернета с Ubuntu на iPhone)

set -e          # Прерывать выполнение при любой ошибке
set -o pipefail # Прерывать, если ошибка в любой части конвейера (pipe)

# Цвета для красивого вывода сообщений
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=========================================================${NC}"
echo -e "${GREEN}    Установщик реверсивного тетеринга для Ubuntu${NC}"
echo -e "${GREEN}=========================================================${NC}"

# Проверка прав суперпользователя
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Ошибка: Этот скрипт должен запускаться от root!${NC}" 
   echo -e "${YELLOW}Пожалуйста, используйте: sudo $0${NC}"
   exit 1
fi

REAL_USER=${SUDO_USER:-$USER}
WORK_DIR="/home/$REAL_USER/Workplace"
CONN_NAME="iPhone USB Shared"

uninstall_reverse_tether() {
    echo -e "${RED}Удаление реверсивного тетеринга...${NC}"

    systemctl stop usbmuxd 2>/dev/null || true
    systemctl disable usbmuxd 2>/dev/null || true
    rm -f /etc/systemd/system/usbmuxd.service
    systemctl daemon-reload

    if nmcli connection show "$CONN_NAME" &>/dev/null; then
        nmcli connection delete "$CONN_NAME"
        echo -e "${GREEN}Подключение '$CONN_NAME' удалено.${NC}"
    fi

    read -p "Удалить исходники в $WORK_DIR? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$WORK_DIR"
        echo -e "${GREEN}Исходники удалены.${NC}"
    fi

    echo -e "${GREEN}Удаление завершено.${NC}"
}

if [[ "${1:-}" == "--uninstall" ]]; then
    uninstall_reverse_tether
    exit 0
fi

# --- Шаг 1: Установка системных зависимостей ---
echo -e "${GREEN}[1/7] Установка системных зависимостей...${NC}"
apt update
apt install -y build-essential pkg-config checkinstall git autoconf automake \
    libtool-bin libplist-dev libusbmuxd-dev libimobiledevice-dev \
    libusb-1.0-0-dev udev curl libcurl4-openssl-dev wget

echo -e "${GREEN}[2/7] Создание рабочей директории...${NC}"
# Используем директорию пользователя, который вызвал sudo
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# --- Шаг 2: Остановка и удаление стандартного usbmuxd (если он установлен) ---
echo -e "${GREEN}[3/7] Остановка и удаление стандартного usbmuxd...${NC}"
systemctl stop usbmuxd 2>/dev/null || true
systemctl disable usbmuxd 2>/dev/null || true
apt remove -y usbmuxd 2>/dev/null || true

# Функция для сборки из исходников
build_from_source() {
    local repo=$1
    local dir=$2
    local url="https://github.com/libimobiledevice/${repo}.git"
    
    echo -e "${GREEN}Сборка и установка ${repo}...${NC}"
    if [ -d "$dir" ]; then
        echo -e "${YELLOW}Директория $dir уже существует. Удаляем для чистой сборки...${NC}"
        rm -rf "$dir"
    fi
    git clone "$url"
    cd "$dir"
    ./autogen.sh
    make
    make install
    cd "$WORK_DIR"
}

# --- Шаг 3: Сборка и установка компонентов в правильной последовательности ---
echo -e "${GREEN}[4/7] Сборка и установка компонентов libimobiledevice...${NC}"
# Порядок важен: сначала базовые библиотеки, затем те, что от них зависят
build_from_source "libplist" "libplist"
build_from_source "libusbmuxd" "libusbmuxd"
build_from_source "libtatsu" "libtatsu"
build_from_source "libimobiledevice" "libimobiledevice"
build_from_source "usbmuxd" "usbmuxd"

# Обновление кеша библиотек
ldconfig

# --- Шаг 4: Настройка сервиса usbmuxd ---
echo -e "${GREEN}[5/7] Настройка usbmuxd как системного сервиса...${NC}"

cat > /etc/systemd/system/usbmuxd.service <<EOF
[Unit]
Description=Socket daemon for multiplexing connections to iOS devices
After=syslog.target

[Service]
Type=simple
ExecStart=/usr/local/sbin/usbmuxd -v -f
Environment=USBMUXD_DEFAULT_DEVICE_MODE=3
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable usbmuxd
systemctl restart usbmuxd

# --- Шаг 5: Проверка статуса usbmuxd ---
echo -e "${GREEN}[6/7] Проверка статуса usbmuxd сервиса...${NC}"
if systemctl is-active --quiet usbmuxd; then
    echo -e "${GREEN}Сервис usbmuxd успешно запущен.${NC}"
else
    echo -e "${RED}Не удалось запустить сервис usbmuxd. Проверьте логи командой: journalctl -u usbmuxd${NC}"
    exit 1
fi

# --- Шаг 6: Создание общего сетевого подключения для iPhone ---
echo -e "${GREEN}[7/7] Создание сетевого подключения с общим доступом...${NC}"
echo -e "${YELLOW}Подключите iPhone к компьютеру через USB и нажмите 'Доверять' на телефоне.${NC}"
read -p "Нажмите Enter, когда устройство будет подключено..."

# Ищем интерфейс iPhone, который обычно начинается с 'enx'
IPHONE_IFACE=$(ip link show | grep -o 'enx[0-9a-f]*' | head -n1)

if [ -z "$IPHONE_IFACE" ]; then
    echo -e "${YELLOW}Интерфейс iPhone не найден. Возможные интерфейсы:${NC}"
    ip link show
    read -p "Введите имя интерфейса вручную (например, enp0s20f0u2): " IPHONE_IFACE
    if [ -z "$IPHONE_IFACE" ]; then
        echo -e "${RED}Ошибка: Имя интерфейса не указано. Выход.${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}Найден интерфейс: $IPHONE_IFACE${NC}"

# Проверяем, существует ли уже подключение с общим доступом для этого интерфейса
if nmcli connection show "$CONN_NAME" &>/dev/null; then
    echo -e "${YELLOW}Подключение '$CONN_NAME' уже существует. Удаляем для обновления...${NC}"
    nmcli connection delete "$CONN_NAME"
fi

# Создаем новое подключение с общим доступом к интернету
nmcli connection add type ethernet ifname "$IPHONE_IFACE" con-name "$CONN_NAME" ipv4.method shared
nmcli connection up "$CONN_NAME"

echo -e "${GREEN}Подключение '$CONN_NAME' настроено и активировано.${NC}"

# --- Финальные инструкции ---
echo -e "${GREEN}=========================================================${NC}"
echo -e "${GREEN}Настройка завершена успешно!${NC}"
echo -e "${GREEN}=========================================================${NC}"
echo -e "${YELLOW}Дальнейшие действия:${NC}"
echo -e "1. На iPhone перейдите в Настройки → Основные → Сброс → Сбросить настройки сети."
echo -e "2. Подключите iPhone к компьютеру через USB и нажмите 'Доверять'."
echo -e "3. На компьютере интернет должен появиться на iPhone автоматически."
echo -e "4. Для проверки статуса сервиса usbmuxd используйте: ${GREEN}systemctl status usbmuxd${NC}"
echo -e "5. Включен ли режим модема на iPhone (необязательно), можно проверить по желанию."
echo -e ""
echo -e "${YELLOW}Чтобы удалить настройки и вернуть всё как было, запустите скрипт с флагом --uninstall:${NC}"
echo -e "  sudo $0 --uninstall"