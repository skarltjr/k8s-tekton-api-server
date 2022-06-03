from flask import Flask
from kube.controller.kube_controller import *

def createApp():
    app = Flask(__name__)
    app.register_blueprint(user_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(deployment_bp)   
    app.register_blueprint(tekton_bp) 
    return app

#
# main
#
app = createApp()
if __name__ == '__main__':
    app.run(host = '0.0.0.0',port = 5001,debug=True)
 