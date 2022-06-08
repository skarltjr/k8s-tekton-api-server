from __future__ import annotations
from kubernetes import client,config
from kubernetes.client.models import V1PersistentVolumeClaimVolumeSource
from flask import Flask,request
from constants.constant import *
from tekton_pipeline import TektonClient
from tekton_pipeline import V1beta1Task
from tekton_pipeline import V1beta1TaskSpec
from tekton_pipeline import V1beta1Step
from tekton_pipeline import V1beta1Pipeline
from tekton_pipeline import V1beta1PipelineSpec
from tekton_pipeline import V1beta1PipelineTask
from tekton_pipeline import V1beta1TaskRef
from tekton_pipeline import V1beta1PipelineRun
from tekton_pipeline import V1beta1PipelineRunSpec
from tekton_pipeline import V1beta1PipelineRef
from tekton_pipeline import V1beta1Param
from tekton_pipeline import V1beta1WorkspacePipelineTaskBinding
from tekton_pipeline import V1beta1PipelineWorkspaceDeclaration
from tekton_pipeline import V1beta1WorkspaceBinding
import os
import base64
import json

def createDeployments():
    #createConfig(CONFIG_PATH)
    # create deployment Object
    container = client.V1Container(
        name="nginx",
        image="nginx:latest",
        ports=[client.V1ContainerPort(container_port=80)],
        resources=client.V1ResourceRequirements(
            requests={"cpu":"100m","memory":"200Mi"},
            limits={"cpu":"500m","memory":"500Mi"}
        )
    )
    # create spec
    template = client.V1PodTemplateSpec(
        metadata = client.V1ObjectMeta(labels={"app":"nginx"}),
        spec=client.V1PodSpec(containers=[container])
    )
    #create deployment Spec
    spec = client.V1DeploymentSpec(
        replicas=3,template=template,selector={
            "matchLabels":{"app":"nginx"}
        }
    )

    # create deployment
    deployment = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(name=DEPLOYMENT_NAME),
        spec=spec
    )

    # deploy
    config_file = CONFIG_PATH2
    config.load_kube_config(config_file=config_file)
    Api_Instance = client.AppsV1Api()
    Api_Instance.create_namespaced_deployment(
        body=deployment,namespace="default"
    )

    #deleteConfig(CONFIG_PATH)
    

def createConfig(configPath):
    configText = request.form['config']
    configFile = open(configPath,"w")
    configFile.write(configText)
    configFile.close()

def deleteConfig(configPath):
    if os.path.isfile(configPath):
        os.remove(configPath)



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
                        V1beta1Param(name = 'deleteExisting',value = 'true'),
                        V1beta1Param(name = 'httpProxy',value = 'http://sec-proxy.k9e.io:3128'),
                        V1beta1Param(name = 'httpsProxy',value = 'http://sec-proxy.k9e.io:3128')
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
                        V1beta1Param(name = 'httpProxy',value = 'http://sec-proxy.k9e.io:3128'),
                        V1beta1Param(name = 'httpsProxy',value = 'http://sec-proxy.k9e.io:3128'),
                        V1beta1Param(name = 'noProxy',value = 'localhost, 127.0.0.1, 127.0.0.0/8, 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, .k9e.io, .kakaoi.com, .kakaoicdn.net, .k9etool.io, .k5d.io, .kakaoenterprise.com, .kakaoicloud.com, .kakaoi.io, .kakaoi.ai, .kakaoicloud.in, github.kakaoenterprise.in, mdock.daumkakao.io, idock.daumkakao.io'),
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
