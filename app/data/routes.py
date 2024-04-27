import json
from typing import Counter
from flask import Blueprint, request, jsonify, send_file, session, redirect, url_for
import pandas as pd
from io import BytesIO
import matplotlib.pyplot as plt
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.probability import FreqDist
from wordcloud import WordCloud
import re
from collections import Counter
import pycountry
import spacy

nltk.download("stopwords")
from firebase_admin import db, storage
from datetime import datetime

import app
from .utils import data_store
from flask_cors import CORS, cross_origin  # type: ignore

nlp = spacy.load("en_core_web_sm")

data_blueprint = Blueprint("data", __name__)


def extract_country(affiliation):
    # Reemplazar "USA" por "United States"
    affiliation = affiliation.replace("USA", "United States")

    # Obtener todos los nombres de los países en inglés
    country_names = [country.name for country in pycountry.countries]  # type: ignore

    # Separar la cadena de afiliación en partes
    parts = affiliation.split(", ")

    # Imprimir todas las partes de la cadena de afiliación
    print("Parts:", parts)

    # Buscar el primer nombre de país válido en las partes
    for part in parts:
        # Intentar extraer el país de la parte de la afiliación
        country = part.strip()
        if country in country_names:
            return country
        elif country == "China" or country == "Peoples R China":
            return "China"

    # Si no se encuentra ningún país válido, devolver None
    return None


@data_blueprint.route("/upload", methods=["POST"])
@cross_origin()
def upload_file():
    print(request.files)

    # Check if both files are provided
    if "scopus_file" not in request.files or "wos_file" not in request.files:
        return jsonify({"error": "Missing Scopus or WoS file parameter"}), 400

    user_uid = request.form.get("user_uid", None)
    scopus_file = request.files["scopus_file"]
    wos_file = request.files["wos_file"]

    cadena_busqueda = request.form.get("cadena_busqueda", "")
    inicio = request.form.get("inicio", "")
    fin = request.form.get("fin", "")

    if not user_uid or not scopus_file or not wos_file:
        return jsonify({"error": "Missing files or user UID"}), 400

    # Check if filenames are provided
    if scopus_file.filename == "" or wos_file.filename == "":
        return jsonify({"error": "One of the files was not selected"}), 400

    # Reading the files into the appropriate DataFrames
    try:
        user_data = {
            "user": user_uid,
            "files": {},
            "cadena_busqueda": cadena_busqueda,
            "inicio": inicio,
            "fin": fin,
            "creacion_registro": datetime.now().isoformat(),  # ISO formatted current date and time
        }

        bucket = storage.bucket()

        if scopus_file:  # Assuming Scopus files are CSVs
            scopus_df = pd.read_csv(scopus_file)  # type: ignore
            data_store["scopus"] = scopus_df  # type: ignore
            scopus_file.seek(0)

            # Upload Scopus file to Firebase Storage
            scopus_blob = bucket.blob(
                f'scopus_files/{user_data["user"]}/{user_data["creacion_registro"]}/{scopus_file.filename}'
            )
            scopus_blob.upload_from_file(
                scopus_file, content_type=scopus_file.content_type
            )
            scopus_blob.make_public()
            user_data["files"]["scopus_file"] = scopus_blob.public_url

        if wos_file:  # Assuming WoS files are Excel files
            wos_df = pd.read_excel(wos_file)
            data_store["wos"] = wos_df  # type: ignore
            wos_file.seek(0)

            # Upload WoS file to Firebase Storage
            wos_blob = bucket.blob(
                f'wos_files/{user_data["user"]}/{user_data["creacion_registro"]}/{wos_file.filename}'
            )
            wos_blob.upload_from_file(wos_file, content_type=wos_file.content_type)
            wos_blob.make_public()
            user_data["files"]["wos_file"] = wos_blob.public_url

        # Firebase
        ref = db.reference("/uploads")
        new_ref = ref.push(user_data)  # type: ignore
        upload_key = new_ref.key

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return (
        jsonify({"message": "Files uploaded successfully", "upload_key": upload_key}),
        200,
    )


def get_country_wos(address):
    # Split the address string and return the country part
    # This is just an example, adapt it to your specific address format
    country = address.split("]")[-1].split(";")[-1].strip()
    return country


@data_blueprint.route("/process", methods=["GET"])
@cross_origin()
def process_data():
    # Check if data has been uploaded
    if data_store["scopus"] is None or data_store["wos"] is None:
        return (
            jsonify(
                {"error": "Scopus and WoS data must be uploaded before processing"}
            ),
            400,
        )

    # Check if any of the data frames are empty
    if data_store["scopus"].empty or data_store["wos"].empty:
        return jsonify({"error": "One of the data sources is empty"}), 400

    try:
        # Start processing for Scopus data
        df_scopus = data_store["scopus"]
        df_scopus["Times Cited"] = df_scopus["Cited by"].apply(
            lambda x: int(x) if pd.notnull(x) else "No data"
        )
        df_scopus["Affiliations"] = df_scopus["Affiliations"].apply(
            lambda x: x.split(",")[-1].strip() if pd.notnull(x) else "No data"
        )
        df_scopus = df_scopus[
            [
                "Authors",
                "Title",
                "Year",
                "Affiliations",
                "Times Cited",
                "DOI",
                "Source title",
                "Abstract",
                "Author Keywords",
                "Document Type",
                "Source",
            ]
        ]
        df_scopus.rename(
            columns={
                "Title": "Article Title",
                "Year": "Publication Year",
                "Source title": "Source Title",
            },
            inplace=True,
        )

        # Start processing for WoS data
        df_wos = data_store["wos"]
        df_wos["Affiliations"] = df_wos["Addresses"].apply(lambda x: get_country_wos(x))
        df_wos = df_wos[
            [
                "Authors",
                "Article Title",
                "Publication Year",
                "Affiliations",
                "Cited Reference Count",
                "DOI",
                "Source Title",
                "Abstract",
                "Author Keywords",
                "Document Type",
            ]
        ]
        df_wos.rename(columns={"Cited Reference Count": "Times Cited"}, inplace=True)
        df_wos["Source"] = "WoS"

        # Merging Scopus and WoS data
        combined_data = pd.concat([df_scopus, df_wos], ignore_index=True)
        combined_data.reset_index(inplace=True, drop=True)

        # Additional processing steps can go here...
        # For example, removing duplicates based on DOI, Article Title, and Abstract.
        combined_data.drop_duplicates(subset="DOI", inplace=True, ignore_index=True)
        combined_data.drop_duplicates(
            subset="Article Title", inplace=True, ignore_index=True
        )
        combined_data.drop_duplicates(
            subset="Abstract", inplace=True, ignore_index=True
        )

        # Perform ranking based on a predefined 'get_q' function
        # Assuming 'get_q' function and 'scimagojr_2020.csv' file are available and correctly implemented in your Flask app
        # df_q = pd.read_csv('/path/to/scimagojr_2020.csv', sep=';')
        # combined_data["Cuartil"] = combined_data["Source Title"].apply(lambda x: get_q(x, df_q))

        # Store the processed data
        data_store["processed"] = combined_data  # type: ignore

        return (
            jsonify(
                {
                    "message": "Data processed successfully",
                    "processed_rows": combined_data.shape[0],
                }
            ),
            200,
        )

    except Exception as e:
        # If any error occurs during processing, catch it and return as internal server error
        return jsonify({"error": str(e)}), 500


@data_blueprint.route("/visualize/<chart_type>", methods=["GET"])
@cross_origin()
def visualize_data(chart_type):
    if data_store["processed"] is None:
        return jsonify({"error": "Data has not been processed"}), 400

    if chart_type not in [
        "keywords",
        "countries",
        "cited_times",
        "authors",
        "publication_years",
        "abstract",
        "institution",
        "most_frequent_keywords",
        "cites",
        "authors_geographic_distribution",
    ]:
        return jsonify({"error": f"Invalid chart type: {chart_type}"}), 400

    # Get the processed data
    processed_data = data_store["processed"]
    processed_data["Affiliations"] = processed_data["Affiliations"].str.replace(
        "USA", "United States"
    )

    if chart_type == "keywords":
        # Proceso de limpieza y conteo de palabras clave
        cleaned_keywords = (
            processed_data["Author Keywords"]
            .str.lower()  # Convertir a minúsculas
            .str.replace(
                r"[^\w\s;]", ""
            )  # Eliminar caracteres no alfanuméricos excepto ;
            .str.split(";")  # Dividir por ;
            .explode()  # Convertir la lista de palabras clave en filas separadas
            .str.strip()  # Eliminar espacios en blanco alrededor de cada palabra clave
        )

        # Contar las palabras clave limpias y encontrar las 10 más frecuentes
        keyword_counts = cleaned_keywords.value_counts().head(10)

        # Convertir los conteos en una lista de diccionarios
        keyword_data = [
            {"keyword": keyword, "frequency": count}
            for keyword, count in keyword_counts.items()  # type: ignore
        ]

        return jsonify({"chart_data": keyword_data})

    elif chart_type == "countries":
        # Count the frequency of each country
        country_counts = (
            processed_data["Affiliations"].apply(extract_country).value_counts()
        )

        # Convert the counts to a list of dictionaries
        country_data = [
            {"country": country, "frequency": count}
            for country, count in country_counts.head(10).items()  # type: ignore
        ]

        return jsonify({"chart_data": country_data})

    elif chart_type == "cited_times":
        # Create a list to store cited times counts for each article title along with row number
        cited_times_data = []

        # Iterate over each row in the processed data
        for index, row in processed_data.iterrows():  # type: ignore
            # Extract article title, cited times, and row number
            title = row["Article Title"]
            cited_times_str = row["Times Cited"]
            row_number = (
                index + 2
            )  # Adding 2 to start counting from 2 (assuming 0-indexing)

            # Convert cited_times_str to an integer if it's not "No data"
            cited_times = int(cited_times_str) if cited_times_str != "No data" else 0

            # Add the article title, cited times, and row number to the list
            cited_times_data.append(
                {"title": title, "cited_times": cited_times, "row_number": row_number}
            )

        # Sort the list by cited times in descending order
        cited_times_data.sort(key=lambda x: x["cited_times"], reverse=True)

        # Limit the list to the first 10 items
        cited_times_data = cited_times_data[:10]

        return jsonify({"chart_data": cited_times_data})

    elif chart_type == "authors":
        # Count the frequency of each author
        author_counts = (
            processed_data["Authors"].str.split(";").explode().value_counts()
        )

        # Convert the counts to a list of dictionaries
        author_data = [
            {"author": author, "frequency": count}
            for author, count in author_counts.head(10).items()  # type: ignore
        ]

        return jsonify({"chart_data": author_data})

    elif chart_type == "publication_years":
        # Extract publication years
        publication_years = processed_data["Publication Year"]

        # Count the frequency of each publication year
        year_counts = publication_years.value_counts().sort_index()

        # Convert the counts to a list of dictionaries
        year_data = [
            {"year": year, "frequency": count} for year, count in year_counts.items()  # type: ignore
        ]

        return jsonify({"chart_data": year_data})

    elif chart_type == "abstract":
        # Extraer texto del abstract
        abstract_text = processed_data["Abstract"].str.cat(sep=" ")

        # Tokenizar el texto (dividir en palabras)
        words = re.findall(r"\b\w+\b", abstract_text.lower())

        # Filtrar palabras vacías
        stop_words = set(stopwords.words("english"))
        words = [word for word in words if word not in stop_words]

        # Contar la frecuencia de cada palabra
        word_counts = Counter(words)

        # Obtener las 10 primeras palabras que más se repiten
        most_common_words = word_counts.most_common(20)

        # Extraer las palabras y sus frecuencias
        top_10_words = [
            {"text": word, "value": count} for word, count in most_common_words
        ]

        return jsonify({"chart_data": top_10_words})

    elif chart_type == "authors_countries":
        # Count the frequency of each country mentioned in the affiliations column
        country_counts = (
            processed_data["Affiliations"]
            .str.extract(r"\b(\w+)\b")
            .stack()
            .value_counts()
        )

        # Convert the counts to a list of dictionaries
        country_data = [
            {"country": country, "frequency": count}
            for country, count in country_counts.items()  # type: ignore
        ]

        return jsonify({"chart_data": country_data})

    # You can implement the other chart types similarly
    else:
        return jsonify({"error": "Chart type not implemented yet"}), 400


@data_blueprint.route("/export", methods=["POST", "OPTIONS"])
@cross_origin(methods=["POST", "OPTIONS"])
def export_data():
    if data_store["processed"] is None:
        return jsonify({"error": "Data has not been processed"}), 400

    folder_id = request.form.get("folder_id")
    if not folder_id:
        return jsonify({"error": "Folder ID is required"}), 400

    # Convert processed DataFrame to Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:  # type: ignore
        data_store["processed"].to_excel(writer, index=False)
    output.seek(0)

    bucket = storage.bucket()
    blob = bucket.blob(f"uploads/{folder_id}/files/processed_data.xlsx")

    blob.upload_from_string(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    blob.make_public()
    url = blob.public_url

    # Update the reference in the Realtime Database
    ref = db.reference(f"uploads/{folder_id}/files")
    ref.update({"processed_data": url})

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="processed_data.xlsx",
    )
