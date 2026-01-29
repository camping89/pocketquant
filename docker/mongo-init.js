// MongoDB initialization script
// Creates indexes for the pocketquant database

db = db.getSiblingDB('pocketquant');

// OHLCV collection indexes
db.ohlcv.createIndex(
  { symbol: 1, exchange: 1, interval: 1, datetime: -1 },
  { unique: true, name: 'idx_ohlcv_unique' }
);

db.ohlcv.createIndex(
  { exchange: 1, symbol: 1 },
  { name: 'idx_ohlcv_symbol_lookup' }
);

print('MongoDB initialization completed');
