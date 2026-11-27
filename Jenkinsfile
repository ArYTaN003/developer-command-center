// Jenkinsfile — reference CI/CD pipeline (artifact for the report).
//
// NOTE: You said you'll do image creation/push and cluster connection manually,
// so this pipeline is provided as a documented reference, not wired to a server.
// It shows path-based change detection, per-service build/push, and rollout.
//
// Credentials expected in Jenkins (not included here):
//   dockerhub-credentials  (username + password)
//   kubeconfig             (secret file)
pipeline {
  agent any

  environment {
    DOCKERHUB_USER = 'YOUR_DOCKERHUB_USER'
    IMAGE_TAG      = "${env.GIT_COMMIT ? env.GIT_COMMIT.take(7) : 'dev'}"
    SERVICES       = 'github-service rag-context-service ai-review-service notification-service'
  }

  stages {
    stage('Checkout') {
      steps { checkout scm }
    }

    stage('Detect changed services') {
      steps {
        script {
          def changed = []
          for (svc in SERVICES.split()) {
            def rc = sh(script: "git diff --name-only HEAD~1 HEAD | grep -q '^services/${svc}/'", returnStatus: true)
            if (rc == 0) { changed << svc }
          }
          if (changed.isEmpty()) { changed = SERVICES.split() as List }  // first build: all
          env.CHANGED = changed.join(' ')
          echo "Changed services: ${env.CHANGED}"
        }
      }
    }

    stage('Test') {
      steps {
        script {
          for (svc in env.CHANGED.split()) {
            sh "echo 'pytest for ${svc} (add tests under services/${svc}/tests)'"
          }
        }
      }
    }

    stage('Build & Push') {
      when { branch 'main' }
      steps {
        withCredentials([usernamePassword(credentialsId: 'dockerhub-credentials',
                         usernameVariable: 'DU', passwordVariable: 'DP')]) {
          sh 'echo "$DP" | docker login -u "$DU" --password-stdin'
          script {
            for (svc in env.CHANGED.split()) {
              def img = "${DOCKERHUB_USER}/${svc}:${IMAGE_TAG}"
              sh "docker build -t ${img} services/${svc}"
              sh "docker push ${img}"
            }
          }
        }
      }
    }

    stage('Deploy to K8s') {
      when { branch 'main' }
      steps {
        withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
          script {
            for (svc in env.CHANGED.split()) {
              def img = "${DOCKERHUB_USER}/${svc}:${IMAGE_TAG}"
              sh "kubectl -n microservices set image deployment/${svc} ${svc}=${img}"
              sh "kubectl -n microservices rollout status deployment/${svc} --timeout=120s"
            }
          }
        }
      }
    }
  }

  post {
    always { sh 'docker logout || true' }
  }
}
