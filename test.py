import docker

from python_on_whales import DockerClient

docker = DockerClient("/home/ubuntu/bt/traffic_gen/seed-compiled")

for i in range(3):
    docker.execute("as112h-traffic_gen-10.112.0.71", ["/bin/bash","-c",f"nohup scion-bwtestserver --listen=:4000{i}"], detach=True)