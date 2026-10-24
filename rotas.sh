#!/bin/bash
# Rotas do Linux Server para a rede do laboratorio (rodar apos cada reinicio do no)
sudo ip route replace 10.0.1.0/24 via 10.0.1.14 dev ens2
for lo in 1.1.1.1 2.2.2.2 3.3.3.3 4.4.4.4; do
  sudo ip route replace $lo/32 via 10.0.1.14 dev ens2
done
sudo ip route replace 172.16.0.0/16 via 10.0.1.14 dev ens2
ip route
