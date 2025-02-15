from datetime import datetime

from flask import request, redirect, Response, abort, render_template, url_for, flash, make_response, send_from_directory, jsonify
from flask.ext.login import login_user , logout_user , current_user, login_required, current_user
from dateutil.parser import parse as dateutil_parse
from flask_yoloapi import endpoint, parameter

import settings
from funding.factory import app, db_session
from funding.orm.orm import Proposal, User, Comment


@app.route('/')
def index():
    return redirect(url_for('proposals'))


@app.route('/about')
def about():
    return make_response(render_template('about.html'))


@app.route('/api')
def api():
    return make_response(render_template('api.html'))


@app.route('/proposal/add/disclaimer')
def proposal_add_disclaimer():
    return make_response(render_template(('proposal/disclaimer.html')))


@app.route('/proposal/add')
def proposal_add():
    if current_user.is_anonymous:
        return make_response(redirect(url_for('login')))
    default_content = settings.PROPOSAL_CONTENT_DEFAULT
    return make_response(render_template('proposal/edit.html', default_content=default_content))


@app.route('/proposal/comment', methods=['POST'])
@endpoint.api(
    parameter('pid', type=int, required=True),
    parameter('text', type=str, required=True),
    parameter('cid', type=int, required=False)
)
def proposal_comment(pid, text, cid):
    if current_user.is_anonymous:
        flash('not logged in', 'error')
        return redirect(url_for('proposal', pid=pid))
    if len(text) <= 3:
        flash('comment too short', 'error')
        return redirect(url_for('proposal', pid=pid))
    try:
        Comment.add_comment(user_id=current_user.id, message=text, pid=pid, cid=cid)
    except Exception as ex:
        flash('Could not add comment: %s' % str(ex), 'error')
        return redirect(url_for('proposal', pid=pid))

    flash('Comment posted.')
    return redirect(url_for('proposal', pid=pid))


@app.route('/proposal/<int:pid>/comment/<int:cid>')
def propsal_comment_reply(cid, pid):
    from funding.orm.orm import Comment
    c = Comment.find_by_id(cid)
    if not c or c.replied_to:
        return redirect(url_for('proposal', pid=pid))
    p = Proposal.find_by_id(pid)
    if not p:
        return redirect(url_for('proposals'))
    if c.proposal_id != p.id:
        return redirect(url_for('proposals'))

    return make_response(render_template('comment_reply.html', c=c, pid=pid, cid=cid))


@app.route('/proposal/<int:pid>')
def proposal(pid):
    p = Proposal.find_by_id(pid=pid)
    p.get_comments()
    if not p:
        return make_response(redirect(url_for('proposals')))
    return make_response(render_template(('proposal/proposal.html'), proposal=p))


@app.route('/api/proposal/add', methods=['POST'])
@endpoint.api(
    parameter('title', type=str, required=True, location='json'),
    parameter('content', type=str, required=True, location='json'),
    parameter('pid', type=int, required=False, location='json'),
    parameter('funds_target', type=str, required=True, location='json'),
    parameter('addr_receiving', type=str, required=True, location='json'),
    parameter('category', type=str, required=True, location='json'),
    parameter('status', type=int, required=True, location='json', default=1)
)
def proposal_api_add(title, content, pid, funds_target, addr_receiving, category, status):
    import markdown2

    if current_user.is_anonymous:
        return make_response(jsonify('err'), 500)

    if len(title) <= 8:
        return make_response(jsonify('title too short'), 500)

    if len(content) <= 20:
        return make_response(jsonify('content too short'), 500)

    if category and category not in settings.FUNDING_CATEGORIES:
        return make_response(jsonify('unknown category'), 500)

    if status not in settings.FUNDING_STATUSES.keys():
        make_response(jsonify('unknown status'), 500)

    if status != 1 and not current_user.admin:
        return make_response(jsonify('no rights to change status'), 500)

    try:
        from funding.bin.anti_xss import such_xss
        content_escaped = such_xss(content)
        html = markdown2.markdown(content_escaped, safe_mode=True)
    except Exception as ex:
        return make_response(jsonify('markdown error'), 500)

    if pid:
        p = Proposal.find_by_id(pid=pid)
        if not p:
            return make_response(jsonify('proposal not found'), 500)

        if p.user.id != current_user.id and not current_user.admin:
            return make_response(jsonify('no rights to edit this proposal'), 500)

        p.headline = title
        p.content = content
        p.html = html
        if addr_receiving:
            p.addr_receiving = addr_receiving
        if category:
            p.category = category

        # detect if an admin moved a proposal to a new status and auto-comment
        if p.status != status and current_user.admin:
            msg = "Moved to status \"%s\"." % settings.FUNDING_STATUSES[status].capitalize()
            try:
                Comment.add_comment(user_id=current_user.id, message=msg, pid=pid, automated=True)
            except:
                pass

        p.status = status
        p.last_edited = datetime.now()
    else:
        try: 
            funds_target = float(funds_target) 
        except Exception as ex:
            return make_response(jsonify('letters detected'),500)
        if funds_target < 1:
                return make_response(jsonify('Proposal asking less than 1 error :)'), 500)
        if len(addr_receiving) != settings.COIN_ADDRESS_LENGTH:
            return make_response(jsonify('Faulty address, should be of length 72'), 500)

        p = Proposal(headline=title, content=content, category='misc', user=current_user)
        p.html = html
        p.last_edited = datetime.now()
        p.funds_target = funds_target
        p.addr_receiving = addr_receiving
        p.category = category
        p.status = status

        db_session.add(p)
        db_session.commit()
        db_session.flush()

        p.addr_donation = Proposal.generate_donation_addr(p)

    db_session.commit()
    db_session.flush()

    # reset cached statistics
    from funding.bin.utils import Summary
    Summary.fetch_stats(purge=True)

    return make_response(jsonify({'url': url_for('proposal', pid=p.id)}))


@app.route('/proposal/<int:pid>/edit')
def proposal_edit(pid):
    p = Proposal.find_by_id(pid=pid)
    if not p:
        return make_response(redirect(url_for('proposals')))

    return make_response(render_template(('proposal/edit.html'), proposal=p))


@app.route('/search')
@endpoint.api(
    parameter('key', type=str, required=False)
)
def search(key=None):
    if not key:
        return make_response(render_template('search.html', results=None, key='Empty!'))
    results = Proposal.search(key=key)
    return make_response(render_template('search.html', results=results, key=key))


@app.route('/user/<path:name>')
def user(name):
    q = db_session.query(User)
    q = q.filter(User.username == name)
    user = q.first()
    return render_template('user.html', user=user)


@app.route('/proposals')
@endpoint.api(
    parameter('status', type=int, location='args', required=False),
    parameter('page', type=int, location='args', required=False),
    parameter('cat', type=str, location='args', required=False)
)
def proposals(status, page, cat):
    if not isinstance(status, int) and not isinstance(page, int) and not cat:
        # no args, render overview
        proposals = {
            'proposed': Proposal.find_by_args(status=1, limit=10),
            'funding': Proposal.find_by_args(status=2, limit=10),
            'wip': Proposal.find_by_args(status=3, limit=10),
            'completed': Proposal.find_by_args(status=4, limit=10)}
        return make_response(render_template('proposal/overview.html', proposals=proposals))

    try:
        if not isinstance(status, int):
            status = 1
        proposals = Proposal.find_by_args(status=status, cat=cat)
    except:
        return make_response(redirect(url_for('proposals')))

    return make_response(render_template('proposal/proposals.html',
                                         proposals=proposals, status=status, cat=cat))


@app.route('/donate')
def donate():
    from funding.bin.daemon import Daemon
    from funding.factory import cache, db_session

    data_default = {'sum': 0, 'txs': []}
    cache_key = 'devfund_txs_in'
    data = cache.get(cache_key)
    if not data:
        daemon = Daemon(url=settings.RPC_LOCATION_DEVFUND,
                        username=settings.RPC_USERNAME_DEVFUND,
                        password=settings.RPC_PASSWORD_DEVFUND)

        txs_in = daemon.get_transfers_in_simple()
        if not txs_in['txs']:
            cache.set(cache_key, data=data_default, expiry=60)
        else:
            txs_in['txs'] = txs_in['txs'][:50]  # truncate to last 50
            cache.set(cache_key, data=txs_in, expiry=60)
    else:
        for tx in data['txs']:
            tx['datetime'] = dateutil_parse(tx['datetime'])
        txs_in = data

    return make_response(render_template('donate.html', txs_in=txs_in))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if settings.USER_REG_DISABLED:
        return 'user reg disabled ;/'

    if request.method == 'GET':
        return make_response(render_template('register.html'))

    username = request.form['username']
    password = request.form['password']
    email = request.form['email']

    try:
        user = User.add(username, password, email)
        flash('Successfully registered. No confirmation email required. You can login!')
        return redirect(url_for('login'))
    except Exception as ex:
        flash('Could not register user. Probably a duplicate username or email that already exists.', 'error')
        return make_response(render_template('register.html'))


@app.route('/login', methods=['GET', 'POST'])
@endpoint.api(
    parameter('username', type=str, location='form'),
    parameter('password', type=str, location='form')
)
def login(username, password):
    if request.method == 'GET':
        return make_response(render_template('login.html'))

    from funding.factory import bcrypt
    user = User.query.filter_by(username=username).first()
    if user is None or not bcrypt.check_password_hash(user.password, password):
        flash('Username or Password is invalid', 'error')
        return make_response(render_template('login.html'))

    login_user(user)
    response = redirect(request.args.get('next') or url_for('index'))
    response.headers['X-Set-Cookie'] = True
    return response


@app.route('/logout', methods=['GET'])
def logout():
    logout_user()
    response = redirect(request.args.get('next') or url_for('login'))
    response.headers['X-Set-Cookie'] = True
    flash('Logout successfully')
    return response


@app.route('/static/<path:path>')
def static_route(path):
    return send_from_directory('static', path)