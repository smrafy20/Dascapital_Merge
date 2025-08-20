def register_blueprints(app):
    from .auth_routes import auth_bp
    from .dashboard_routes import dashboard_bp
    from .money_routes import money_bp
    from .statement_routes import statement_bp
    from .payee_routes import payee_bp
    from .profile_routes import profile_bp
    from .notification_routes import notification_bp
    from .request_routes import requests_bp
    from .split_routes import split_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(money_bp)
    app.register_blueprint(statement_bp)
    app.register_blueprint(payee_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(requests_bp)
    app.register_blueprint(split_bp)
 