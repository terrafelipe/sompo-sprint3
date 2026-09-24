-- Runs after the fleet assertions (farms still live) and before the deletion assertions.
select pg_temp.check_true((select count(*)=4 from fazenda),'mapa: farms preserved');
select pg_temp.check_true((select count(*)=4 from fazenda where latitude is null and longitude is null),'mapa: coordinates start empty');
set role service_role;
update fazenda set latitude=-22.7253, longitude=-47.6492 where id_fazenda=2;
reset role;
select pg_temp.check_true((select latitude=-22.7253 and longitude=-47.6492 from fazenda where id_fazenda=2),'mapa: service saves coordinates');
select pg_temp.rejects($q$update fazenda set latitude=91, longitude=0 where id_fazenda=3$q$,'mapa: latitude out of range');
select pg_temp.rejects($q$update fazenda set latitude=0, longitude=-181 where id_fazenda=3$q$,'mapa: longitude out of range');
select pg_temp.rejects($q$update fazenda set latitude=-10 where id_fazenda=3$q$,'mapa: latitude without longitude');
update fazenda set latitude=null, longitude=null where id_fazenda=2;
select 'ALL MAP SQL ASSERTIONS PASSED' result;
