FROM public.ecr.aws/lambda/python:3.13 as stage

RUN dnf install -y sudo unzip
ENV CHROMIUM_VERSION=1002910

# Install Chromium
COPY install-browser.sh /tmp/
RUN /usr/bin/bash /tmp/install-browser.sh

FROM public.ecr.aws/lambda/python:3.13 as base

COPY chrome-deps.txt /tmp/
RUN dnf install -y $(cat /tmp/chrome-deps.txt)

# Install Python dependencies for function
COPY requirements.txt /tmp/
RUN python3 -m pip install --upgrade pip -q
RUN python3 -m pip install -r /tmp/requirements.txt -q

COPY --from=stage /opt/chrome /opt/chrome
COPY --from=stage /opt/chromedriver /opt/chromedriver

# copy crawler.py
COPY crawler.py /var/task/

WORKDIR /var/task

CMD [ "crawler.handler" ]