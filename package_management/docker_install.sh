#!/bin/bash

# Проверка прав администратора
if [ "$(id -u)" != "0" ]; then
    echo "Этот скрипт должен запускаться с правами root." 1>&2
    exit 1
fi

# Определение дистрибутива
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "Не удалось определить дистрибутив Linux"
    exit 1
fi

# Установка Docker в зависимости от дистрибутива
case $OS in
    ubuntu|debian)
        echo "Установка Docker для Ubuntu/Debian"
        
        # Обновление пакетов
        apt-get update -y
        
        # Установка зависимостей
        apt-get install -y apt-transport-https ca-certificates curl software-properties-common
        
        # Добавление ключа Docker
        curl -fsSL https://download.docker.com/linux/$OS/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
        
        # Добавление репозитория
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
        https://download.docker.com/linux/$OS $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
        
        # Установка Docker
        apt-get update -y
        apt-get install -y docker-ce docker-ce-cli containerd.io
        ;;
    
    centos|fedora)
        echo "Установка Docker для CentOS/Fedora"
        
        # Установка зависимостей
        if [ "$OS" = "centos" ]; then
            yum install -y yum-utils
        else
            dnf install -y dnf-plugins-core
        fi
        
        # Добавление репозитория
        if [ "$OS" = "centos" ]; then
            yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        else
            dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
        fi
        
        # Установка Docker
        if [ "$OS" = "centos" ]; then
            yum install -y docker-ce docker-ce-cli containerd.io
        else
            dnf install -y docker-ce docker-ce-cli containerd.io
        fi
        ;;
        
    *)
        echo "Неподдерживаемый дистрибутив: $OS"
        exit 1
        ;;
esac

# Включение и запуск Docker
systemctl enable --now docker

# Проверка установки
docker --version
if [ $? -eq 0 ]; then
    echo "Docker успешно установлен!"
    echo "Запускаем тестовый контейнер..."
    docker run hello-world
else
    echo "Произошла ошибка при установке Docker."
    exit 1
fi