# Aluisyo Funding System

The main aim of the Aluisyo Funding System is to enable community members to complete projects and be paid for the projects by other community members.


## Installation

#### Daemon

Make sure the daemon is up.

```bash
./aluisyod
```

#### Wallet RPC

Expose walletd via RPC.

```bash
./walletd --rpc-bind-port 19000 --disable-rpc-login --wallet-file afs --password ""
```


#### Web application

Download application and configure.

```
sudo apt install libjpeg-dev libpng-dev python-virtualenv python3 redis-server postgresql-server postgresql-server-dev-*
git clone https://github.com/aluisyonetwork/aluisyo-funding-system.git
cd aluisyo-funding-systemwownero-wfs
virtualenv -p /usr/bin/python3
source venv/bin/activate
pip uninstall pillow
pip install -r requirements.txt
CC="cc -mavx2" pip install -U --force-reinstall pillow-simd
cp settings.py_example settings.py
- change settings accordingly
```

Prepare a database in postgres and create an user for it.

Run the application:

```bash
python run_dev.py
```

Beware `run_dev.py` is meant as a development server.

When running behind nginx/apache, inject `X-Forwarded-For`.

### License

© 2019 WTFPL – Do What the Fuck You Want to Public License
