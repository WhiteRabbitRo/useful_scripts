# Шпаргалка по основным командам Docker

##

### Вывести список образов
```bash
docker images
```

#
# docker ps 				                    – вывести список контейнеров
#
# docker build [OPTIONS] . 	                    – построить образ 
# -t <name>[:<tag>]			                    – дать имя образу (+тэг)
#
# docker run [OPTIONS] <image_name> [COMMAND]   – запустить контейнер с образом image_name 
# -d 						                    – запустить фоном (без вывода в терминал)
# -p <port_num>:<port_num> 	                    –  обозначить лист доступных портов для подключения к контейнеру
#
# --net <net_name> 			                    – назначить сетевые настройки
# --ip=<ip>					                    – назначить ip-адрес
#
# docker network create --subnet 10.0.3.0/24 --gateway=10.0.3.1 --ip-range 10.0.3.0/24 --driver=bridge --label=my_network coap_network1
#
# docker network ls 			                – вывести список созданных сетей
# docker network inspect <net_name>	            – вывести информацию о сети

