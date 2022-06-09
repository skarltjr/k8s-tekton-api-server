# k8s-practice-python
```
소스코드 클론 -> 이미지 빌드 -> 도커 레지스트리 푸쉬 일련의 pipeline을 
어떤 k8s 클러스터에든 자동으로 구축해주는 api 서버

유저는 pipeline을 구성하고자하는 k8s클러스터의 config 및 repo주소, 도커 계정정보등을 전달해주면
원하는 k8s클러스터에 tekton pipeline이 구성되고 실행되어 사용자가 전달한 repo를 클론받아 빌드 후 docker registry에 이미지를 푸쉬한다
```

# Issue 1
- https://github.com/tektoncd/experimental/issues/885
```
처음 활용해보는 오픈소스라 예제를 참고해야했다
그런데 예제가 잘못된 부분도 있고 변경된 파라미터도 있었다
마침 tekton client도 내부적으로 python k8s client를 활용하고 있어서 두 오픈소스의 내부 코드를 보면서 이에 맞춰 활용활 수 있었고 이슈를 남겼다.
```
# Issue 2
- 사내망은 제한적인 네트워크
```
사내망은 제한적인 네트워크라 문제가 많았다.

1. 문제 상황 1 : k8s api 활용 막힘 
처음엔 308 status code를 로그에서 확인했다.
처음보는 상태코드였고 308 -> 500으로 끝나 "redirection"에 집중했다.
요청 처리 과정은 user -> cluster내 app -> user 클러스터에 접근 -> pipeline생성 -> 응답
redirection이 일어난다면 어디서일어날까 고민했고 ⭐️cluster내 app -> user 클러스터에 접근⭐️라 생각했다.
application은 사용자 요청이오면 내부에서 사용자 클러스터에 한 번더 접근하기 때문이라고 생각.


해결 : 쿠버네티스는 모든 요청이 api server를 통해 전달된다. 그리고 지금 이 api서버에 접근하지못했다.
이유는 바로 모든 쿠버네티스 api server는 6443포트를 사용하고 사내망에선 따로 요청을 하지 않으면 뚫려있지않다. 
뚫어서 해결했다.

2. 문제 상황 2: 사내망에서 외부로 요청을 내보내기위해선 프록시를 함께 태워야했다.
결국 깃허브, 도커허브는 외부 서비스이고 이 외부 서비스 접근을 위해서 위를 수행해야했다.

git-clone, dockerhub push task를 수행하는 pipeline 생성 k8s api요청에 파라미터를 추가했다
V1beta1Param(name = 'httpProxy',value = 'http://xxxxx'),
V1beta1Param(name = 'httpsProxy',value = 'http://xxxx')

```

## 1. task
```
# Tekton pipeline v0.23.0 설치
kubectl apply -f https://storage.googleapis.com/tekton-releases/pipeline/previous/v0.23.0/release.yaml

git-clone task를 적용합니다
kubectl apply -f https://raw.githubusercontent.com/tektoncd/catalog/main/task/git-clone/0.5/git-clone.yaml

buildah task를 적용합니다
kubectl apply -f https://raw.githubusercontent.com/tektoncd/catalog/main/task/buildah/0.3/buildah.yaml
```
```
buildah custom
- 프록시 정보 추가를 위해서라면 아래 buildah task를 apply

---
apiVersion: tekton.dev/v1beta1
kind: Task
metadata:
  name: buildah
  labels:
    app.kubernetes.io/version: "0.3"
  annotations:
    tekton.dev/categories: Image Build
    tekton.dev/pipelines.minVersion: "0.17.0"
    tekton.dev/tags: image-build
    tekton.dev/platforms: "linux/amd64,linux/s390x,linux/ppc64le,linux/arm64"
spec:
  description: >-
    Buildah task builds source into a container image and
    then pushes it to a container registry.

    Buildah Task builds source into a container image using Project Atomic's
    Buildah build tool.It uses Buildah's support for building from Dockerfiles,
    using its buildah bud command.This command executes the directives in the
    Dockerfile to assemble a container image, then pushes that image to a
    container registry.

  params:
  - name: IMAGE
    description: Reference of the image buildah will produce.
  - name: BUILDER_IMAGE
    description: The location of the buildah builder image.
    default: quay.io/buildah/stable:v1.18.0
  - name: STORAGE_DRIVER
    description: Set buildah storage driver
    default: overlay
  - name: DOCKERFILE
    description: Path to the Dockerfile to build.
    default: ./Dockerfile
  - name: CONTEXT
    description: Path to the directory to use as context.
    default: .
  - name: TLSVERIFY
    description: Verify the TLS on the registry endpoint (for push/pull to a non-TLS registry)
    default: "true"
  - name: FORMAT
    description: The format of the built container, oci or docker
    default: "oci"
  - name: BUILD_EXTRA_ARGS
    description: Extra parameters passed for the build command when building images.
    default: ""
  - name: PUSH_EXTRA_ARGS
    description: Extra parameters passed for the push command when pushing images.
    type: string
    default: ""
  - name: SKIP_PUSH
    description: Skip pushing the built image
    default: "false"
  - name: httpProxy
    description: git HTTP proxy server for non-SSL requests
    type: string
    default: ""
  - name: httpsProxy
    description: git HTTPS proxy server for SSL requests
    type: string
    default: ""
  - name: noProxy
    description: git no proxy - opt out of proxying HTTP/HTTPS requests
    type: string
    default: ""
  workspaces:
  - name: source
  - name: sslcertdir
    optional: true
  results:
  - name: IMAGE_DIGEST
    description: Digest of the image just built.
  steps:
  - name: build
    env:
      - name: HTTP_PROXY
        value: $(params.httpProxy)
      - name: HTTPS_PROXY
        value: $(params.httpsProxy)
      - name: NO_PROXY
        value: $(params.noProxy)
    image: $(params.BUILDER_IMAGE)
    workingDir: $(workspaces.source.path)
    script: |
      [[ "$(workspaces.sslcertdir.bound)" == "true" ]] && CERT_DIR_FLAG="--cert-dir $(workspaces.sslcertdir.path)"
      buildah ${CERT_DIR_FLAG} --storage-driver=$(params.STORAGE_DRIVER) bud \
        $(params.BUILD_EXTRA_ARGS) --format=$(params.FORMAT) \
        --tls-verify=$(params.TLSVERIFY) --no-cache \
        -f $(params.DOCKERFILE) -t $(params.IMAGE) $(params.CONTEXT)
    volumeMounts:
    - name: varlibcontainers
      mountPath: /var/lib/containers
    securityContext:
      privileged: true

  - name: push
    env:
      - name: HTTP_PROXY
        value: $(params.httpProxy)
      - name: HTTPS_PROXY
        value: $(params.httpsProxy)
      - name: NO_PROXY
        value: $(params.noProxy)
    image: $(params.BUILDER_IMAGE)
    workingDir: $(workspaces.source.path)
    script: |
      [[ "$(params.SKIP_PUSH)" == "true" ]] && echo "Push skipped" && exit 0
      [[ "$(workspaces.sslcertdir.bound)" == "true" ]] && CERT_DIR_FLAG="--cert-dir $(workspaces.sslcertdir.path)"
      buildah ${CERT_DIR_FLAG} --storage-driver=$(params.STORAGE_DRIVER) push \
        $(params.PUSH_EXTRA_ARGS) --tls-verify=$(params.TLSVERIFY) \
        --digestfile $(workspaces.source.path)/image-digest $(params.IMAGE) \
        docker://$(params.IMAGE)
    volumeMounts:
    - name: varlibcontainers
      mountPath: /var/lib/containers
    securityContext:
      privileged: true

  - name: digest-to-results
    image: $(params.BUILDER_IMAGE)
    script: cat $(workspaces.source.path)/image-digest | tee /tekton/results/IMAGE_DIGEST

  volumes:
  - name: varlibcontainers
    emptyDir: {}

```

## 2. pv,pvc
- pv,pvc 생성 후 적용합니다.
- 해당 볼륨은 pipeline에서 workspace로 사용합니다.
- pv
```
apiVersion: v1
kind: PersistentVolume
metadata:
  name: standard2
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  capacity:
    storage: 5Gi
  hostPath:
    path: /data
```
- pvc
```
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: testpvc
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 5G
```
## 3. pipeline
- 유저에게 config, git repo 주소, 도커 레지스트리 주소 및 계정정보를 전달받습니다
- 이를 활용하여 pipeline을 구성합니다
- task간 볼륨을 공유하여 이전 작업 내용을 활용합니다
```
#
# tekton pipeline services
#
def createTektonPipeline():
    createConfig(CONFIG_PATH)
    config_file = CONFIG_PATH    

    # create  client
    config.load_kube_config(config_file=config_file)
    k8s_client = client.CoreV1Api()
    tekton_client = TektonClient(config_file=config_file)
    gitAddress = request.form['gitAddress']
    dockerRegistry = request.form['registry']

    # create docker secret
    createDockerSecret(k8s_client)

    # create docker service account
    createDockerServiceAccount(k8s_client)
    
    # define a task
    # git-clone task는 미리 클러스터에 올리기

    # Define the pipeline
    pipeline = V1beta1Pipeline(
        api_version='tekton.dev/v1beta1',
        kind='Pipeline',
        metadata=client.V1ObjectMeta(name='sample-pipeline'),
        spec=V1beta1PipelineSpec(
            workspaces = [
                V1beta1PipelineWorkspaceDeclaration(name = 'pipeline-shared-data')
            ],
            tasks=[
                V1beta1PipelineTask(
                    name='git-clone',
                    task_ref=V1beta1TaskRef(name='git-clone'),
                    params = [
                        V1beta1Param(name = 'url',value = gitAddress),
                        V1beta1Param(name = 'revision',value = 'main'),
                        V1beta1Param(name = 'deleteExisting',value = 'true')
                    ],
                    workspaces=[
                        V1beta1WorkspacePipelineTaskBinding(name = 'output', workspace = 'pipeline-shared-data')
                    ]
                ),
                V1beta1PipelineTask(
                    name = 'build-image',
                    run_after = ['git-clone'],
                    task_ref = V1beta1TaskRef(name ='buildah'),
                    params = [
                        V1beta1Param(name = 'IMAGE',value = f'{dockerRegistry}:$(tasks.git-clone.results.commit)')
                    ],
                    workspaces=[
                        V1beta1WorkspacePipelineTaskBinding(name = 'source', workspace = 'pipeline-shared-data')
                    ]
                )
            ]
        ))


    # Create the pipeline
    tekton_client.create(tekton=pipeline, namespace='default')
```

## 3-1. secret & service account 생성
- 도커레지스트리 접근을 위한 sa 생성을 위해 계정정보를 전달받은 후 secret생성 -> sa 생성 -> pipelineRun에서 활용
```
def createDockerSecret(k8s_client): 
    # create docker secret
    username = request.form['docker-username']
    password = request.form['docker-password']
    email = request.form['docker-email']
    # echo -n 'username:password'|base64의 결과물을 전달받는다.
    auth = request.form['docker-auth']
    docker_credential_payload = {
    "auths": {
        "https://index.docker.io/v1/": {
            "username": username,
            "password": password,
            "email": email,
            "auth" : auth
            }
        }
    }

    data = {
        ".dockerconfigjson": base64.b64encode(
            json.dumps(docker_credential_payload).encode()
        ).decode()
    }

    secret = client.V1Secret(
        api_version="v1",
        data=data,
        kind="Secret",
        metadata=dict(name="my-docker-secret", namespace="default"),
        type="kubernetes.io/dockerconfigjson",
    )
    k8s_client.create_namespaced_secret("default", body=secret)
    
    
    
    
 def createDockerServiceAccount(k8s_client):
    sa = {
        'apiVersion':'v1',
        'kind':'ServiceAccount',
        'metadata':{
            'name':'my-docker-sa'
        },
        'secrets':[{
            'name':'my-docker-secret'
        }]
    }
    k8s_client.create_namespaced_service_account(namespace='default', body=sa)

```

## 5. pipeline 실행을 위한 pipelineRun을 구성합니다
- 도커 레지스트리에 접근을 위해 미리 만들어둔 service account를 활용합니다
```
    # define pipelineRun
    pipelinerun = V1beta1PipelineRun(
    api_version='tekton.dev/v1beta1',
    kind='PipelineRun',
    metadata=client.V1ObjectMeta(name='sample-pipelinerun'),
    spec=V1beta1PipelineRunSpec(
        service_account_name = 'my-docker-sa',
        pipeline_ref=V1beta1PipelineRef(
            name='sample-pipeline'),
        workspaces = [
            V1beta1WorkspaceBinding(
                name = 'pipeline-shared-data',
                persistent_volume_claim = V1PersistentVolumeClaimVolumeSource(
                    claim_name = 'testpvc'
                )
            )
        ]
    ))


    tekton_client.create(tekton=pipelinerun, namespace='default')


    deleteConfig(CONFIG_PATH)

```


### 참고
- https://github.com/kubernetes-client/python
- https://github.com/tektoncd/experimental

