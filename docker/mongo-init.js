// MongoDB initialization script
// This runs on first container startup

db = db.getSiblingDB('pocketquant');

// Create collections with validation schemas
db.createCollection('ohlcv', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['symbol', 'exchange', 'interval', 'datetime', 'open', 'high', 'low', 'close', 'volume'],
            properties: {
                symbol: { bsonType: 'string', description: 'Trading symbol' },
                exchange: { bsonType: 'string', description: 'Exchange name' },
                interval: { bsonType: 'string', description: 'Time interval (1m, 5m, 1h, 1d, etc)' },
                datetime: { bsonType: 'date', description: 'Bar datetime' },
                open: { bsonType: 'double', description: 'Open price' },
                high: { bsonType: 'double', description: 'High price' },
                low: { bsonType: 'double', description: 'Low price' },
                close: { bsonType: 'double', description: 'Close price' },
                volume: { bsonType: 'double', description: 'Volume' }
            }
        }
    }
});

// Create indexes for efficient querying
db.ohlcv.createIndex(
    { symbol: 1, exchange: 1, interval: 1, datetime: -1 },
    { unique: true, name: 'idx_ohlcv_unique' }
);

db.ohlcv.createIndex(
    { symbol: 1, interval: 1, datetime: -1 },
    { name: 'idx_symbol_interval_datetime' }
);

db.ohlcv.createIndex(
    { datetime: -1 },
    { name: 'idx_datetime' }
);

// Collection for tracking data sync status
db.createCollection('sync_status');
db.sync_status.createIndex(
    { symbol: 1, exchange: 1, interval: 1 },
    { unique: true, name: 'idx_sync_status_unique' }
);

// Collection for symbol metadata
db.createCollection('symbols');
db.symbols.createIndex(
    { symbol: 1, exchange: 1 },
    { unique: true, name: 'idx_symbols_unique' }
);

print('MongoDB initialization completed successfully');
