import os
import urllib.request
from flask import Flask, request, jsonify,render_template,send_file, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS, cross_origin
from common.arguments import parse_args
from common.camera import *
from common.loss import *
from common.model import *
from common.utils import add_path
from numpy import *
from bvh_skeleton import h36m_skeleton
import numpy as np
import pandas as pd
import shutil

add_path()

UPLOAD_FOLDER = 'fileUploads'
DOWNLOAD_FOLDER = 'bvh_files/fileUploads'


app = Flask(__name__,template_folder='./flaskApp/template')
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})
app.config['CORS_HEADERS'] = 'Content-Type'
app.secret_key = "secret key"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER


ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif','csv'])


def allowed_file(filename):
	return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def rowsToDic(df):
    dic = {}
    for index, row in df.iterrows():
        dic[index] = row
    return dic


def dicToMatrix(dic):
    n = len(dic.keys())
    result = np.zeros((n, 17, 3))
    for i in range(n):
        row = dic[i]
        index = 0
        for j in range(17):
            sub_data = row[index:index + 3]
            result[i, j, :] = sub_data
            index += 3
    return result


def dataSmooth(data):
    data = data.drop(['Timestamp'], axis=1)
    for (columnName, columnData) in data.iteritems():
        for i in range(len(columnData) - 10):
            subData = columnData[i:i + 10]
            subSum = sum(subData)
            avgSub = subSum / len(subData)
            columnData[i] = avgSub
    # print(data)
    return data

# Data Format in CSV file
'''
order :
spinebase(hips) : 0 (4 on data.xlsx)
hipright(rightupleg):1 (12 on data.xlsx)
kneeright(rightleg):2 (14 on data.xlsx)
ankleright(rightfoot):3 (16 on data.xlsx)
hipleft(leftupleg):4 (11 on data.xlsx)
kneeleft(leftleg):5 (13 on data.xlsx)
ankleleft(leftfoot):6 (15 on data.xlsx)
spineMid(spine):7 (3 on data.xlsx)
spineshoulder(spine1):8 (2 on data.xlsx)
neck(neck):9 (1 on data.xlsx)
head(headEndSite):10 (0 on data.xlsx)
leftShoulder(leftarm):11 (5 on data.xlsx)
leftelbow(leftforearm):12 (7 on data.xlsx)
leftwrist(lefthand):13 (9 on data.xlsx)
rightShoulder(rightarm):14 (6 on data.xlsx)
rightelbow(rightforearm):15 (8 on data.xlsx)
rightwrist(righthand):16 (10.xlsx)
'''


def matrixConversion(matrix):
    final_matrix = np.zeros(matrix.shape)
    for i in range(matrix.shape[0]):
        final_matrix[i, 0, :] = matrix[i, 4, :]
        final_matrix[i, 1, :] = matrix[i, 12, :]
        final_matrix[i, 2, :] = matrix[i, 14, :]
        final_matrix[i, 3, :] = matrix[i, 16, :]
        final_matrix[i, 4, :] = matrix[i, 11, :]
        final_matrix[i, 5, :] = matrix[i, 13, :]
        final_matrix[i, 6, :] = matrix[i, 15, :]
        final_matrix[i, 7, :] = matrix[i, 3, :]
        final_matrix[i, 8, :] = matrix[i, 2, :]
        final_matrix[i, 9, :] = matrix[i, 1, :]
        final_matrix[i, 10, :] = matrix[i, 0, :]
        final_matrix[i, 11, :] = matrix[i, 5, :]
        final_matrix[i, 12, :] = matrix[i, 7, :]
        final_matrix[i, 13, :] = matrix[i, 9, :]
        final_matrix[i, 14, :] = matrix[i, 6, :]
        final_matrix[i, 15, :] = matrix[i, 8, :]
        final_matrix[i, 16, :] = matrix[i, 10, :]
    return final_matrix


def dataProcess(data):
    data_dic = rowsToDic(data)
    m = dicToMatrix(data_dic)
    final_m = matrixConversion(m)
    return final_m

@app.route('/')
@cross_origin()
def uploadForm():
    return render_template('index.html')


@app.route("/api/v1/csvToBvh",methods=["POST"])
@cross_origin()
def convert_csv_to_bvh():
    for root, dirs, files in os.walk('./fileUploads'):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))
    
    for root, dirs, files in os.walk('./bvhFiles/fileUploads'):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))
    
    if 'file' not in request.files:
        resp = jsonify({'message' : 'No file part in the request'})
        resp.status_code = 400
        return resp
    file = request.files['file']
    full_filepath='./fileUploads/'+file.filename 
    data=pd.read_csv(file)
    data = dataSmooth(data)
    prediction = dataProcess(data)
    prediction = prediction.astype(float)
    # rot = np.array([0.14070565, -0.15007018, -0.7552408, 0.62232804], dtype=np.float32)
    rot = np.array([0.14, -0.15, -0.755, 0.75], dtype=np.float32)
    prediction = camera_to_world(prediction, R=rot, t=0)
    prediction[:, :, 2] -= np.min(prediction[:, :, 2])
    prediction_copy = np.copy(prediction)
    outputpath = "bvhFiles/"
    write_standard_bvh(outputpath,prediction_copy,full_filepath)

    if file.filename == '':
        resp = jsonify({'message' : 'No file selected for uploading'})
        resp.status_code = 400
        return resp
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        resp = jsonify({'message' : 'File successfully uploaded'})
        resp.status_code = 201
        originalFileName=filename.split('.')[0]+'.bvh'
        # print(os.path.join(app.config['DOWNLOAD_FOLDER']))
        try:
            return send_file('./bvhFiles/fileUploads/'+originalFileName,as_attachment=True)
        except FileNotFoundError:
            abort(404)

    else:
        resp = jsonify({'message' : 'Allowed file types are txt, pdf, png, jpg, jpeg, gif'})
        resp.status_code = 400
        return resp

def write_standard_bvh(outbvhfilepath,prediction3dpoint,filename):

    for frame in prediction3dpoint:
        for point3d in frame:
            point3d[0] *= 100
            point3d[1] *= 100
            point3d[2] *= 100

            X = point3d[0]
            Y = point3d[1]
            Z = point3d[2]

            point3d[0] = X + 100
            point3d[1] = -Z + 175
            point3d[2] = Y + 200

    dir_name = os.path.dirname(outbvhfilepath)
    basename = os.path.basename(outbvhfilepath)
    video_name = basename[:basename.rfind('.')]
    bvhfileDirectory = os.path.join(dir_name,video_name)
    if not os.path.exists(bvhfileDirectory):
        os.makedirs(bvhfileDirectory)
    f_name = filename[0:-3]
    f_name = f_name + "bvh"
    bvhfileName = os.path.join(dir_name,f_name)
    human36m_skeleton = h36m_skeleton.H36mSkeleton()
    human36m_skeleton.poses2bvh(prediction3dpoint,output_file=bvhfileName)

if __name__ == "__main__":
    app.run(host='0.0.0.0',debug=True,threaded=True)