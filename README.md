# k8s-practice-python
```
소스코드 클론 -> 이미지 빌드 -> 도커 레지스트리 푸쉬 일련의 pipeline을 
어떤 k8s 클러스터에든 자동으로 구축해주는 api 서버

유저는 pipeline을 구성하고자하는 k8s클러스터의 config 및 repo주소, 도커 계정정보등을 전달해주면
원하는 k8s클러스터에 pipeline이 구성된다
```

## 1. task
```
git-clone task를 적용합니다
kubectl apply -f https://raw.githubusercontent.com/tektoncd/catalog/main/task/git-clone/0.5/git-clone.yaml

buildah task를 적용합니다
kubectl apply -f https://raw.githubusercontent.com/tektoncd/catalog/main/task/buildah/0.3/buildah.yaml
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

