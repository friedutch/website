from app import create_app, init_project_dbs

app = create_app()

if __name__ == "__main__":
    init_project_dbs()
    app.run(host="127.0.0.1", port=5001)
