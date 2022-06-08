from crypt import methods
from ..services.kube_service import createDeployments,createTektonPipeline
from flask import jsonify,Blueprint
import base64

user_bp = Blueprint('user', __name__, url_prefix='/user')
config_bp = Blueprint('config',__name__,url_prefix='/config')
deployment_bp = Blueprint('deployment',__name__,url_prefix='/deployment')
tekton_bp = Blueprint('tekton-pipeline',__name__,url_prefix='/tekton')


@deployment_bp.route('/create',methods=['POST'])
def createDeployApi():
    createDeployments()
    return jsonify({
        "message" : "deployment 생성 완료"
    })

@tekton_bp.route('/',methods=['POST'])
def createPipelineApi():
    createTektonPipeline()
    return jsonify({
        "message" : "test test"
    })


@tekton_bp.route("/test",methods=['GET'])
def hello():
        return jsonify({
        "message" : "oh!!"
    })