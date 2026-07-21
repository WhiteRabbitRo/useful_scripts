# Шпаргалка по основным командам Docker

## Образы

### Вывести список образов
```bash
docker images
```

### Построить образ
```bash
docker build -t myapp:latest .
```

## Контейнеры

### Вывести список контейнеров
```bash
docker ps          # запущенные
docker ps -a       # все
```

### Запустить контейнер
```bash
docker run -d --name mycontainer myapp:latest
docker run -it --rm ubuntu:22.04 bash
```

### Остановить и удалить
```bash
docker stop mycontainer
docker rm mycontainer
docker rm -f mycontainer   # принудительно
```

## Порты и сеть

### Проброс портов
```bash
docker run -d -p 8080:80 --name web nginx
```

### Создать сеть
```bash
docker network create \
  --subnet 10.0.3.0/24 \
  --gateway 10.0.3.1 \
  --ip-range 10.0.3.0/24 \
  --driver bridge \
  --label=my_network \
  coap_network1
```

### Управление сетями
```bash
docker network ls
docker network inspect coap_network1
```

### Запуск с сетевыми настройками
```bash
docker run --net coap_network1 --ip 10.0.3.10 myapp:latest
```

## Полезные команды

```bash
docker logs mycontainer
docker exec -it mycontainer bash
docker system df
docker system prune    # очистка неиспользуемых ресурсов
```
