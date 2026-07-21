#!/usr/bin/env bash
set -euo pipefail

# Проверка прав администратора
if [[ "$(id -u)" != "0" ]]; then
    echo "Этот скрипт должен запускаться с правами root." >&2
    exit 1
fi

# Определение дистрибутива
if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS="$ID"
    CODENAME="${VERSION_CODENAME:-}"
else
    echo "Не удалось определить дистрибутив Linux"
    exit 1
fi

if [[ -z "$CODENAME" ]] && command -v lsb_release &>/dev/null; then
    CODENAME="$(lsb_release -cs)"
fi

if [[ -z "$CODENAME" ]]; then
    echo "Не удалось определить codename дистрибутива (VERSION_CODENAME / lsb_release)" >&2
    exit 1
fi

# Установка Docker в зависимости от дистрибутива
case $OS in
    ubuntu|debian)
        echo "Установка Docker для Ubuntu/Debian ($CODENAME)"

        apt-get update -y
        apt-get install -y apt-transport-https ca-certificates curl gnupg

        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL "https://download.docker.com/linux/${OS}/gpg" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg

        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${OS} ${CODENAME} stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

        apt-get update -y
        apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        ;;

    centos|fedora)
        echo "Установка Docker для CentOS/Fedora"

        if [[ "$OS" = "centos" ]]; then
            yum install -y yum-utils
            yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            yum install -y docker-ce docker-ce-cli containerd.io
        else
            dnf install -y dnf-plugins-core
            dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
            dnf install -y docker-ce docker-ce-cli containerd.io
        fi
        ;;

    *)
        echo "Неподдерживаемый дистрибутив: $OS"
        exit 1
        ;;
esac

systemctl enable --now docker

if docker --version; then
    echo "Docker успешно установлен!"
    echo "Запускаем тестовый контейнер..."
    docker run hello-world
else
    echo "Произошла ошибка при установке Docker."
    exit 1
fi
