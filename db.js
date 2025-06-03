const { Pool } = require('pg');

const pool = new Pool({
  user: 'postgres',
  host: 'localhost',
  database: 'accessibility_map',
  password: '040494',
  port: 5432,
});

module.exports = pool;