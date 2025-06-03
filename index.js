// línies inicials i imports
console.log("Iniciant servidor...");

import express from 'express';
import session from 'express-session';
import { Pool } from 'pg';
import bcrypt from 'bcrypt';
import bodyParser from 'body-parser';
import path from 'path';
import { fileURLToPath } from 'url';
import fetch from 'node-fetch'; 
import { exec, spawn } from 'child_process'; 

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const port = 3000;

// Connexió PostgreSQL
const pool = new Pool({
  user: 'postgres',
  host: 'localhost',
  database: 'accessibility_map',
  password: '040494',
  port: 5432
});

// Configuració general
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static('forms'));

app.use(session({
  secret: 'clau-secreta',
  resave: false,
  saveUninitialized: true
}));

// Redirecció inicial
app.get('/', (req, res) => {
  res.redirect('/login');
});

// --- REGISTRE ---
app.get('/register', (req, res) => {
  res.render('register');
});

app.post('/register', async (req, res) => {
  const { nom, password } = req.body;
  try {
    const hashedPassword = await bcrypt.hash(password, 10);
    const result = await pool.query(
      'INSERT INTO users (nom, password) VALUES ($1, $2) RETURNING id',
      [nom, hashedPassword]
    );
    req.session.userId = result.rows[0].id;
    res.redirect('/pre_form');
  } catch (err) {
    if (err.code === '23505') {
      res.send('Aquest usuari ja existeix. <a href="/login">Inicia sessió</a>');
    } else {
      console.error(err);
      res.status(500).send('Error creant l’usuari');
    }
  }
}); 

// --- LOGIN ---
app.get('/login', (req, res) => {
  res.render('login');
});

app.post('/login', async (req, res) => {
  const { nom, password } = req.body;
  try {
    const result = await pool.query('SELECT id, password FROM users WHERE nom = $1', [nom]);
    if (result.rows.length === 0) return res.send('Usuari no trobat. <a href="/register">Registra’t</a>');

    const user = result.rows[0];
    const validPassword = await bcrypt.compare(password, user.password);
    if (!validPassword) return res.send('Contrasenya incorrecta. <a href="/login">Torna a provar</a>');

    req.session.userId = user.id;
    res.redirect('/pre_form');
  } catch (err) {
    console.error(err);
    res.status(500).send('Error d’inici de sessió');
  }
});

// --- LOGOUT ---
app.get('/logout', (req, res) => {
  req.session.destroy(() => {
    res.redirect('/login');
  });
});

// --- FORMULARI 1 ---
app.get('/pre_form', (req, res) => {
  if (!req.session.userId) return res.redirect('/login');
  res.render('pre_form');
});

app.post('/submit', async (req, res) => {
  if (!req.session.userId) return res.redirect('/login');
  const d = req.body;

  try {
    const result = await pool.query(`
      INSERT INTO pre_form_answers (
        tipus_discapacitat, mobilitat_elements, evitar_escales,
        dificultats_rampes, baranes, preferencia_pendents, carrers_estrets,
        zones_descans, evitar_soroll, userid
      ) VALUES (
        $1, $2, $3, $4, $5, $6, $7,
        $8, $9, $10
      ) RETURNING id`,
      [
        Array.isArray(d.tipus_discapacitat) ? d.tipus_discapacitat : [d.tipus_discapacitat],
        Array.isArray(d.mobilitat_elements) ? d.mobilitat_elements : [d.mobilitat_elements],
        d.evitar_escales === 'Sí',
        d.dificultats_rampes === 'Sí',
        d.baranes === 'Sí',
        d.preferencia_pendents === 'Sí',
        d.carrers_estrets === 'Sí',
        d.zones_descans || null,
        d.evitar_soroll === 'Sí',
        req.session.userId
      ]
    );
    const insertedId = result.rows[0].id;
    res.redirect(`/search/${insertedId}`);
  } catch (err) {
    console.error(err);
    res.status(500).send('Error en desar la resposta del primer formulari');
  }
});

// --- CERCA ---
app.get('/search/:preFormId', (req, res) => {
  if (!req.session.userId) return res.redirect('/login');
  const preFormId = req.params.preFormId;
  res.render('search', { 
    preFormId,
    originName: '',
    destName: '',
    originLat: null,
    originLon: null,
    destLat: null,
    destLon: null
  });
});

app.post('/search', async (req, res) => {
  if (!req.session.userId) return res.redirect('/login');

  const { origin, destination, preFormId } = req.body;

  const geocode = async (query) => {
    const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=1`;
    const response = await fetch(url, {
      headers: { 'User-Agent': 'AccessibilityMap/1.0' }
    });
    const data = await response.json();
    if (!data || data.length === 0) return null;
    return {
      lat: parseFloat(data[0].lat),
      lon: parseFloat(data[0].lon),
      osmid: parseInt(data[0].osm_id)
    };
  };

  try {
    const originGeo = await geocode(origin);
    const destinationGeo = await geocode(destination);

    if (!originGeo || !destinationGeo) {
      return res.send('No s’han trobat coordenades per l’origen o el destí. Torna-ho a provar.');
    }

    const result = await pool.query(
      `INSERT INTO searches (
        userid, fk_preform_id, origin, origin_lat, origin_lon, origin_osmid,
        destination, dest_lat, dest_lon, dest_osmid
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
      RETURNING id`,
      [
        req.session.userId,
        preFormId,
        origin,
        originGeo.lat,
        originGeo.lon,
        originGeo.osmid,
        destination,
        destinationGeo.lat,
        destinationGeo.lon,
        destinationGeo.osmid
      ]
    );

    const searchId = result.rows[0].id;
    res.redirect(`/mapa/${searchId}`);
  } catch (err) {
    console.error(err);
    res.status(500).send('Error processant la cerca.');
  }
});

// --- MAPA ---
app.get('/mapa/:searchId', async (req, res) => {
  if (!req.session.userId) return res.redirect('/login');

  const searchId = req.params.searchId;
  const userId = req.session.userId;

  try {
    const result = await pool.query(`
      SELECT fk_preform_id FROM searches 
      WHERE id = $1 AND userid = $2
      LIMIT 1
    `, [searchId, userId]);

    if (result.rows.length === 0) {
      return res.status(404).send("No s'ha trobat la cerca");
    }

    const preFormId = result.rows[0].fk_preform_id;

    // Executar script Python
    const pythonPath = 'python';
    const scriptPath = path.join(__dirname, 'funcio_cerca_rutes.py');
    const args = [userId.toString(), preFormId.toString()];

    const pythonProcess = spawn(pythonPath, [scriptPath, ...args]);

    let output = '';
    pythonProcess.stdout.on('data', (data) => {
      output += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      console.error(`Error Python: ${data}`);
    });

    pythonProcess.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).send('Error en calcular la ruta');
      }
      try {
        const geojson = JSON.parse(output);
        res.render('mapa', { geojson, searchId });
      } catch (err) {
        console.error('Error parsejant GeoJSON:', err);
        res.status(500).send('Error processant la ruta');
      }
    });

  } catch (err) {
    console.error(err);
    res.status(500).send("Error carregant les dades de la cerca");
  }
});

// --- FORMULARI 2 ---
app.get('/post_form/:id', (req, res) => {
  if (!req.session.userId) return res.redirect('/login');
  const idAnswer = req.params.id;
  res.render('post_form', { idAnswer });
});

app.post('/post_submit', async (req, res) => {
  if (!req.session.userId) return res.redirect('/login');

  const d = req.body;
  try {
    await pool.query(`
      INSERT INTO post_form_answers (
        answer_id, transitabilitat, amplada_voreres, carrers_dificultats,
        obstacles, descans, passos_accessibles, seguretat,
        percentatge_accessibilitat, comentaris
      ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
      )`,
      [
        d.idAnswer,
        d.transitabilitat === 'Sí',
        d.amplada_voreres === 'Sí',
        d.carrers_dificultats,
        d.obstacles,
        d.descans,
        d.passos_accessibles === 'Sí',
        d.seguretat === 'Sí',
        parseInt(d.percentatge_accessibilitat),
        d.comentaris
      ]
    );

    res.send('Resposta post-ruta registrada correctament! <a href="/pre_form">Torna al formulari</a>');
  } catch (err) {
    console.error(err);
    res.status(500).send('Error en desar la resposta post-ruta');
  }
});

// --- INICI SERVIDOR ---
app.listen(port, () => {
  console.log(`Servidor actiu a http://localhost:${port}`);
});
