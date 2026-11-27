# Local Jenkins LTS image with plugins + Configuration-as-Code baked in.
# Credentials (dockerhub-credentials, kubeconfig, github-token) are provisioned
# from placeholders in jenkins/.env via JCasC — no manual UI clicking.
FROM jenkins/jenkins:lts-jdk17

USER root
# docker CLI (build/push stages) + kubectl (rollout stage). Arch-aware kubectl.
RUN apt-get update && apt-get install -y --no-install-recommends \
      docker.io curl ca-certificates \
    && ARCH="$(dpkg --print-architecture)" \
    && curl -fsSLo /usr/local/bin/kubectl \
       "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/${ARCH}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

USER jenkins
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli -f /usr/share/jenkins/ref/plugins.txt

COPY casc/jenkins.yaml /var/jenkins_conf/jenkins.yaml
ENV CASC_JENKINS_CONFIG=/var/jenkins_conf/jenkins.yaml
# Skip the setup wizard; admin user comes from JCasC/.env instead.
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
