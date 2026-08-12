# PocketQuant TODO
- ops: mongodump bar collections before running any repair/destructive endpoint from a local session (Option 2b has full write creds to prod Mongo)
- ops: restrict VPS ports 52017/53679/54900 to own IP via firewall (currently open to internet, password-only)
- ops: pin docker image tags (git SHA or date) instead of :latest on next deploy, for rollback ability
- uxui - change to claude AI theme, both dark and light
- on charts page, remove the dot line for indicators (e.g. EMA)
- in the strategies page, show the same indicator list as the charts page - reuse the code, do not write duplicated code
- in backtest page, default start date and end date values are 1 year from now back to the past. Start date and end date should allow minutes as well
- on the top right, next to the dropdown of timezone, show current clock
- refactor to use latest next js version due to AI docs and features
- makesure code for datetime conversion is working (FE use local then convert to
- UTC on server
  Trạng thái cuối — 2 plan sẵn sàng                                                                                 
                                                                                                                    
  - 260630-0031-backtest-research-workbench/ (4 phase) — qua brainstorm + red-team + validate. Active. Failed: 0, đủ
  điều kiện implement.                                                                                              
  - 260630-0031-backtest-mae-mfe-excursion/ (3 phase) — blockedBy workbench, redesign timing broker-path.