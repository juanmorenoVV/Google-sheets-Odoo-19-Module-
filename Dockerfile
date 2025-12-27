FROM odoo:19

USER root

# Instalamos git y dependencias del sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copiamos el archivo de requerimientos
COPY ./requirements.txt /etc/odoo/requirements.txt

# INSTALACIÓN CON EL FLAG DE SEGURIDAD
RUN pip install --no-cache-dir --break-system-packages -r /etc/odoo/requirements.txt

USER odoo