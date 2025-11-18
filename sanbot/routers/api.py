"""REST API routes."""
from __future__ import annotations

import os
from typing import Set

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from file_analyzer import FileAnalyzer


def _allowed_file(filename: str, allowed_extensions: Set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def create_api_blueprint(
    file_analyzer: FileAnalyzer,
    upload_folder: str,
    allowed_extensions: Set[str],
) -> Blueprint:
    bp = Blueprint("analysis_api", __name__)

    @bp.route("/api/analyze", methods=["POST"])
    def analyze_files():  # type: ignore[override]
        try:
            if "file1" not in request.files or "file2" not in request.files:
                return jsonify({"success": False, "error": "Both file1 and file2 are required"}), 400

            file1 = request.files["file1"]
            file2 = request.files["file2"]
            instruction = request.form.get("instruction", "对比两个文件的差异")

            if file1.filename == "" or file2.filename == "":
                return jsonify({"success": False, "error": "Both files must have valid filenames"}), 400

            if not (_allowed_file(file1.filename, allowed_extensions) and _allowed_file(file2.filename, allowed_extensions)):
                return (
                    jsonify({
                        "success": False,
                        "error": f"File types not allowed. Allowed types: {allowed_extensions}",
                    }),
                    400,
                )

            filename1 = secure_filename(file1.filename)
            filename2 = secure_filename(file2.filename)
            file1_path = os.path.join(upload_folder, f"temp_1_{filename1}")
            file2_path = os.path.join(upload_folder, f"temp_2_{filename2}")

            file1.save(file1_path)
            file2.save(file2_path)

            result = file_analyzer.analyze_files(file1_path, file2_path, instruction)

            try:
                os.remove(file1_path)
                os.remove(file2_path)
            except OSError:
                current_app.logger.warning("Failed to remove temporary files", exc_info=True)

            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            current_app.logger.exception("API analysis failed")
            return jsonify({"success": False, "error": str(exc)}), 500

    return bp
