from flask import Blueprint, make_response, request, redirect, url_for, \
    session, render_template, current_app, send_from_directory
import json
import sys
import os
import gzip
import requests
from uuid import uuid4
from werkzeug import secure_filename
from csvkit import convert
from csvkit.unicsv import UnicodeCSVReader
from csvkit.cleanup import RowChecker
from cStringIO import StringIO
from geomancer.helpers import import_class, get_geo_types, get_data_sources, \
    get_geo_types, guess_geotype
from geomancer.app_config import ALLOWED_EXTENSIONS, \
    MAX_CONTENT_LENGTH, MANCERS

views = Blueprint('views', __name__)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

# primary pages
@views.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

@views.route('/about', methods=['GET', 'POST'])
def about():
    return render_template('about.html')

@views.route('/upload-formats', methods=['GET', 'POST'])
def upload_formats():
    return render_template('upload-formats.html')

@views.route('/contribute-data', methods=['GET', 'POST'])
def contribute_data():
    return render_template('contribute-data.html')

@views.route('/geographies', methods=['GET', 'POST'])
def geographies():
    geographies = get_geo_types()
    return render_template('geographies.html', geographies=geographies)

@views.route('/data-sources', methods=['GET', 'POST'])
def data_sources():
    data_sources = get_data_sources()
    return render_template('data-sources.html', data_sources=data_sources)

# routes for geomancin'
@views.route('/upload/', methods=['GET', 'POST'])
def upload():
    context = {}
    if request.method == 'POST':
        f = request.files['input_file']
        if f:
            if allowed_file(f.filename):
                inp = StringIO(f.read())
                if sys.getsizeof(inp.getvalue()) <= MAX_CONTENT_LENGTH:
                    inp.seek(0)
                    file_format = convert.guess_format(f.filename)
                    try:
                        converted = convert.convert(inp, file_format)
                    except UnicodeDecodeError:
                        context['errors'] = ['We had a problem with reading your file. \
                            This could have to do with the file encoding or format']
                        converted = None
                    f.seek(0)
                    if converted:
                        outp = StringIO(converted)
                        reader = UnicodeCSVReader(outp)
                        session['header_row'] = reader.next()
                        rows = []
                        columns = [[] for c in session['header_row']]
                        column_ids = range(len(session['header_row']))
                        for row in range(100):
                            try:
                                rows.append(reader.next())
                            except StopIteration:
                                break
                        for i, row in enumerate(rows):
                            for j,d in enumerate(row):
                                columns[j].append(row[column_ids[j]])
                        sample_data = []
                        for index, header_val in enumerate(session['header_row']):
                            geotype_guess = guess_geotype(header_val, columns[index])
                            sample_data.append((index, header_val, columns[index], geotype_guess))
                        session['sample_data'] = sample_data
                        outp.seek(0)
                        session['file'] = outp.getvalue()
                        session['filename'] = f.filename
                        return redirect(url_for('views.select_geo'))
                else:
                   context['errors'] = ['Uploaded file must be 10mb or less.'] 
            else:
                context['errors'] = ['Only .xls or .xlsx and .csv files are allowed.']
        else:
            context['errors'] = ['You must provide a file to upload.']
    return render_template('upload.html', **context)

@views.route('/select-geography/', methods=['GET', 'POST'])
def select_geo():
    if not session.get('file'):
        return redirect(url_for('views.index'))
    context = {}
    if request.method == 'POST':
        inp = StringIO(session['file'])
        reader = UnicodeCSVReader(inp)
        header = reader.next()
        fields = {}
        geo_type = None
        valid = True
        if not request.form:
            valid = False
            context['errors'] = ['Select a field that contains a geography type']
        else:
            geotypes = []
            indexes = []
            for k,v in request.form.items():
                if k.startswith("geotype"):
                    geotypes.append(v)
                    indexes.append(k.split('_')[1])
            fields_key = ';'.join([header[int(i)] for i in indexes])
            geotype_val = ';'.join([g for g in geotypes])
            fields[fields_key] = {
                'geo_type': geotype_val,
                'column_index': ';'.join(indexes)
            }

            # found_geo_type = get_geo_types(geo_type)[0]['info']
            # sample_list = session['sample_data'][index][2]
            # valid, message = found_geo_type.validate(sample_list)
            # context['errors'] = [message]
        if valid:
            mancer_data = get_data_sources(geo_type)
            session.update({'fields': fields, 'mancer_data': mancer_data})
            return redirect(url_for('views.select_tables'))
    return render_template('select_geo.html', **context)

@views.route('/select-tables/', methods=['POST', 'GET'])
def select_tables():
    if not session.get('file'):
        return redirect(url_for('views.index'))
    context = {}
    if request.method == 'POST' and not request.form:
        valid = False
        context['errors'] = ['Select at least on table to join to your spreadsheet']
    context.update({'fields': session['fields'], 'mancer_data': session['mancer_data']})
    return render_template('select_tables.html', **context)

@views.route('/geomance/<session_key>/')
def geomance_view(session_key):
    return render_template('geomance.html', session_key=session_key)

@views.route('/download/<path:filename>')
def download_results(filename):
    return send_from_directory(current_app.config['RESULT_FOLDER'], filename)
