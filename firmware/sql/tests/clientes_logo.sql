-- Runs after the ESP32 assertions; customer 1 is archived, customer 2 is live.
select pg_temp.check_true((select count(*)=1 from pg_constraint where conname='cliente_logo_url_https'),'logo check created once');
update cliente set logo_url='https://exemplo.com/logo.png' where id_cliente=2;
select pg_temp.check_true((select logo_url='https://exemplo.com/logo.png' from cliente where id_cliente=2),'https logo accepted');
update cliente set logo_url='https://'||repeat('a',492) where id_cliente=2;
select pg_temp.check_true((select char_length(logo_url)=500 from cliente where id_cliente=2),'500 characters accepted');
update cliente set logo_url=null where id_cliente=2;
select pg_temp.check_true((select logo_url is null from cliente where id_cliente=2),'logo removable');
select pg_temp.rejects($q$update cliente set logo_url='http://exemplo.com/logo.png' where id_cliente=2$q$,'http logo rejected');
select pg_temp.rejects($q$update cliente set logo_url='javascript:alert(1)' where id_cliente=2$q$,'javascript logo rejected');
select pg_temp.rejects($q$update cliente set logo_url='data:image/png;base64,AAAA' where id_cliente=2$q$,'data logo rejected');
select pg_temp.rejects($q$update cliente set logo_url='https://'||repeat('a',493) where id_cliente=2$q$,'logo over 500 rejected');
select pg_temp.rejects($q$insert into cliente(id_cliente,nome,logo_url) values(50,'Novo','http://x')$q$,'insert checks logo');
select 'ALL CUSTOMER LOGO SQL ASSERTIONS PASSED' result;
