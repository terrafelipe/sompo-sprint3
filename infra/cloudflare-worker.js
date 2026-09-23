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
    // Host fixo na Function URL; so path e query vem do pedido. NAO usar
    // new URL(path, base): um path '//evil.com/x' vira URL absoluta e o Worker
    // mandaria o cookie de sessao da vitima para outro host (proxy aberto).
    const destino = new URL(env.LAMBDA_URL);
    destino.pathname = origem.pathname;
    destino.search = origem.search;

    return fetch(destino, {
      method: request.method,
      headers: request.headers, // o fetch troca o Host pelo da Function URL
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
      redirect: 'manual', // redirects (ex.: /login) voltam para o navegador
    });
  },
};
