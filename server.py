from run import app
from app import init_project_dbs

if __name__ == "__main__":
    init_project_dbs()
    app.run(host="127.0.0.1", port=5001)
