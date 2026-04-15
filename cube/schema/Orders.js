cube(`Orders`, {
  sql: `SELECT * FROM orders`,

  measures: {
    totalAmount: {
      sql: `amount`,
      type: `sum`,
    },
  },

  dimensions: {
    id: {
      sql: `id`,
      type: `number`,
      primaryKey: true,
    },

    createdAt: {
      sql: `created_at`,
      type: `time`,
    },
  },
});
