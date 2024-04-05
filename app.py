from flask import Flask, request, jsonify, send_file
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from flask_cors import CORS, cross_origin

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

Debug = True


# Storage for uploaded data
data_store = {"scopus": None, "wos": None, "processed": None}


@app.route("/upload", methods=["POST"])
@cross_origin()
def upload_file():
    print(request.files)

    # Check if both files are provided
    if "scopus_file" not in request.files or "wos_file" not in request.files:
        return jsonify({"error": "Missing Scopus or WoS file parameter"}), 400

    scopus_file = request.files["scopus_file"]
    wos_file = request.files["wos_file"]

    # Check if filenames are provided
    if scopus_file.filename == "" or wos_file.filename == "":
        return jsonify({"error": "One of the files was not selected"}), 400

    # Reading the files into the appropriate DataFrames
    try:
        if scopus_file:  # Assuming Scopus files are CSVs
            data_store["scopus"] = pd.read_csv(scopus_file)
        if wos_file:  # Assuming WoS files are Excel files
            data_store["wos"] = pd.read_excel(wos_file)
    except Exception as e:
        app.logger.error(f"Failed to read file: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Files uploaded successfully"}), 200


def get_country_wos(address):
    # Split the address string and return the country part
    # This is just an example, adapt it to your specific address format
    country = address.split("]")[-1].split(";")[-1].strip()
    return country


@app.route("/process", methods=["GET"])
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
        data_store["processed"] = combined_data

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
        app.logger.error(f"Error during processing: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/visualize/keywords", methods=["GET"])
@cross_origin()
def visualize_keywords():
    if data_store["processed"] is None:
        return jsonify({"error": "Data has not been processed"}), 400
    # Generate a keywords frequency plot (customize this based on your actual data)
    fig, ax = plt.subplots()
    # Example plotting code; replace with your actual visualization logic
    ax.bar(["Keyword A", "Keyword B"], [50, 30])
    ax.set_xlabel("Keywords")
    ax.set_ylabel("Frequency")
    plt.title("Top Keywords Frequency")
    # Save plot to a bytes buffer
    buf = BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", as_attachment=False)


@app.route("/export", methods=["GET"])
@cross_origin()
def export_data():
    if data_store["processed"] is None:
        return jsonify({"error": "Data has not been processed"}), 400

    # Convert processed DataFrame to Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        data_store["processed"].to_excel(writer, index=False)
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="processed_data.xlsx",
    )


if __name__ == "__main__":
    app.run(debug=True)
