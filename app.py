from flask import Flask, request, jsonify, send_file
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import base64


app = Flask(__name__)
Debug = True


# Storage for uploaded data
data_store = {"scopus": None, "wos": None, "processed": None}


@app.route("/upload", methods=["POST"])
def upload_file():
    print(request.files)
    print(request.form)
    if "file" not in request.files:
        return jsonify({"error": "Missing file parameter"}), 400
    elif "source" not in request.form:
        return jsonify({"error": "Missing source parameter"}), 400
    file = request.files["file"]
    source = request.form["source"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    if source.lower() not in ["scopus", "wos"]:
        return jsonify({"error": "Invalid source specified"}), 400
    # Reading the file into the appropriate DataFrame
    try:
        if source == "scopus":
            data_store["scopus"] = pd.read_excel(file)
        elif source == "wos":
            data_store["wos"] = pd.read_csv(file)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"message": f"{source} file uploaded successfully"}), 200


@app.route("/process", methods=["GET"])
def process_data():
    if not data_store["scopus"] or not data_store["wos"]:
        return (
            jsonify(
                {"error": "Scopus and WoS data must be uploaded before processing"}
            ),
            400,
        )
    # Merging and processing data
    combined_data = pd.concat(
        [data_store["scopus"], data_store["wos"]], ignore_index=True
    )
    # Implement specific processing steps here based on your data structure and needs
    # Example: Removing duplicates based on DOI
    combined_data.drop_duplicates(subset="DOI", inplace=True, ignore_index=True)
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


@app.route("/visualize/keywords", methods=["GET"])
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
def export_data():
    if data_store["processed"] is None:
        return jsonify({"error": "Data has not been processed"}), 400
    # Convert processed DataFrame to Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        data_store["processed"].to_excel(writer, index=False)
    output.seek(0)
    return send_file(
        output, attachment_filename="processed_data.xlsx", as_attachment=True
    )


if __name__ == "__main__":
    app.run(debug=True)
