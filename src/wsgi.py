from main import app, initialize_robot


initialize_robot()


def application(environ, start_response):
    return app(environ, start_response)
