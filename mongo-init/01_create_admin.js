// mongo-init/01_create_admin.js
// Ce script est exécuté automatiquement par le conteneur MongoDB au premier démarrage.
// Il crée le compte admin avec les droits root.

db = db.getSiblingDB('admin');

db.createUser({
  user: 'admin',
  pwd: 'smartrecruit2026',
  roles: [
    { role: 'root', db: 'admin' }
  ]
});

print('✅ Utilisateur admin créé avec succès sur la base admin.');
