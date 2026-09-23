// Cloudflare Worker que da uma URL limpa (sompo-painel.<conta>.workers.dev) para o
// painel na Lambda. Repassa a requisicao inteira para a Function URL e devolve a
// resposta sem mexer (inclusive o Set-Cookie, que nao tem Domain e por isso fica
// gravado no dominio do Worker).
//
// Configurar no dashboard do Cloudflare: Workers > sompo-painel > Settings >
// Variables > LAMBDA_URL = https://<id>.lambda-url.us-east-1.on.aws (sem barra final).

export default {
  async fetch(request, env) {
    const origem = new URL(request.url);
    const destino = new URL(origem.pathname + origem.search, env.LAMBDA_URL);

    const headers = new Headers(request.headers);
    headers.set('X-Forwarded-Host', origem.host);
    headers.set('X-Forwarded-Proto', 'https');

    return fetch(destino, {
      method: request.method,
      headers, // o fetch troca o Host pelo da Function URL automaticamente
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
      redirect: 'manual', // redirects (ex.: /login) voltam para o navegador
    });
  },
};
