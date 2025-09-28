# 도커 빌드 명령어
docker build --platform linux/x86_64 -t exchange-rate-crawler -f Dockerfile .

# 태그 변경
docker tag {로컬컨테이너태그} {ECR컨테이너태그}

