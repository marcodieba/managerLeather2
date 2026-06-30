# Use a imagem base Python
FROM python:3.9

# Definir variáveis de ambiente
ARG DEBIAN_FRONTEND=noninteractive

ENV LANG=pt_BR.UTF-8 \
    LANGUAGE=pt_BR.UTF-8 \
    LC_ALL=pt_BR.UTF-8 \
    PYTHONUNBUFFERED=1 \
    # Railway definirá a porta correta no momento da execução
    PORT=8000

# Atualiza lista de pacotes e instala dependências necessárias
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        apt-utils \
        locales \
        redis-tools \
        dumb-init \
        httpie \
        python3-pip \
        python3-setuptools \
        gettext \
        libpq-dev && \
    echo "$LANG UTF-8" > /etc/locale.gen && \
    locale-gen

# Criação do usuário 'srv'
RUN useradd -m -d /srv srv

# Define o diretório de trabalho e atribui permissões
WORKDIR /srv
RUN chown -R srv:srv /srv

# Copia os arquivos de dependências
COPY --chown=srv:srv requirements.txt /srv/

# Instala as dependências Python
RUN pip install --no-cache-dir pip --upgrade && \
    pip install --no-cache-dir -r requirements.txt

# Instala pacotes adicionais
RUN pip install gunicorn daphne whitenoise psycopg2

# Usa o Dumb-init como entrypoint
ENTRYPOINT ["/usr/bin/dumb-init", "--"]

# CMD padrão, Railway definirá a variável de ambiente PORT
CMD /usr/local/bin/daphne -b 0.0.0.0 -p ${PORT:-8000} core.asgi:application

# Copia o código fonte da aplicação
COPY --chown=srv:srv ./src /srv

# Executa o collectstatic no build
# RUN python manage.py collectstatic --noinput
