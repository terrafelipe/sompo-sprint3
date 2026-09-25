// Proxy do Cloudflare Pages (modo avancado: _worker.js) que da a URL limpa
// https://sompo-painel.pages.dev para o painel na Lambda. Repassa a requisicao
// inteira para a Function URL e devolve a resposta sem mexer (inclusive o
// Set-Cookie, que nao tem Domain e por isso fica gravado no dominio do Pages).
//
// Publicar: Workers & Pages > Create > Pages > Upload assets, enviando a pasta
// infra/pages (so este arquivo). Ou: npx wrangler pages deploy infra/pages --project-name sompo-painel

// Function URL da Lambda (sem barra final). Nao e segredo: o login do Flask protege
// o site. A variavel LAMBDA_URL do projeto Pages, se existir, tem prioridade.
const LAMBDA_URL_PADRAO = 'https://wtyrjjdaask5krlxdhtt57eidq0kdqsn.lambda-url.us-east-1.on.aws';

export default {
  async fetch(request, env) {
    const origem = new URL(request.url);
    // Host fixo na Function URL; so path e query vem do pedido. NAO usar
    // new URL(path, base): um path '//evil.com/x' vira URL absoluta e o proxy
    // mandaria o cookie de sessao da vitima para outro host (proxy aberto).
    const destino = new URL(env.LAMBDA_URL || LAMBDA_URL_PADRAO);
    destino.pathname = origem.pathname;
    destino.search = origem.search;

    // Segredo compartilhado (variavel PROXY_SEGREDO do projeto Pages = PROXY_SEGREDO da Lambda):
    // com ele o Flask confia no CF-Connecting-IP (IP real do visitante) no limite de tentativas
    // do login. O valor que o visitante mandar nesse cabecalho e sempre descartado.
    const headers = new Headers(request.headers);
    headers.delete('X-Sompo-Proxy');
    if (env.PROXY_SEGREDO) headers.set('X-Sompo-Proxy', env.PROXY_SEGREDO);

    return fetch(destino, {
      method: request.method,
      headers, // o fetch troca o Host pelo da Function URL
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
      redirect: 'manual', // redirects (ex.: /login) voltam para o navegador
    });
  },
};
